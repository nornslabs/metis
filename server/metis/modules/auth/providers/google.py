"""Google sign-in: OAuth 2.0 Authorization Code + PKCE with OpenID Connect.

No auth SDK: ``httpx`` for the discovery document, the code exchange and the
JWKS; ``PyJWT`` to verify the ``id_token`` (``RS256`` only; signature, ``iss``,
``aud``, ``exp``, then ``nonce``). Discovery and JWKS are cached per provider
instance for :data:`METADATA_TTL`. A ``kid`` the cached JWKS lacks triggers
one refetch (Google rotated its keys), at most once per
:data:`FORCED_JWKS_REFRESH_INTERVAL` so forged tokens cannot hammer Google.

Every failure is an ``OAuthFailedError`` logged with a safe ``step`` and
``reason``; the code, verifier, tokens and client secret are never logged.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from metis.core.errors import OAuthFailedError, UpstreamError
from metis.helpers.http import ClientFactory, FailureReason, send
from metis.modules.auth.providers.base import (
    AuthProviderName,
    OAuthFailure,
    OAuthStep,
    ProviderProfile,
    oauth_failed,
)

DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
SCOPES = "openid email profile"
ID_TOKEN_ALGORITHM = "RS256"
ID_TOKEN_LEEWAY = timedelta(seconds=30)
METADATA_TTL = timedelta(hours=1)
FORCED_JWKS_REFRESH_INTERVAL = timedelta(minutes=1)
JSON_HEADERS = {"Accept": "application/json"}
PKCE_METHOD = "S256"
ACCOUNT_PROMPT = "select_account"
PROVIDER = AuthProviderName.GOOGLE
_UPSTREAM_FAILURES = {
    FailureReason.UNAUTHORIZED.value: OAuthFailure.REJECTED,
    FailureReason.UNREACHABLE.value: OAuthFailure.UNREACHABLE,
    FailureReason.TIMEOUT.value: OAuthFailure.TIMEOUT,
}

Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class _Discovery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    authorization_endpoint: str = Field(min_length=1)
    token_endpoint: str = Field(min_length=1)
    jwks_uri: str = Field(min_length=1)


class _TokenResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id_token: str = Field(min_length=1)


class _IdTokenClaims(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    sub: str = Field(min_length=1)
    email: str = Field(min_length=1)
    email_verified: bool = False
    name: str | None = None
    picture: str | None = None
    nonce: str = Field(min_length=1)


@dataclass(frozen=True)
class _Cached[T]:
    value: T
    fetched_at: datetime


def _parse[ModelT: BaseModel](model: type[ModelT], body: Any, step: OAuthStep) -> ModelT:
    """Validate a Google response body, or fail the sign-in as ``bad_response``."""
    try:
        return model.model_validate(body)
    except ValidationError:
        raise oauth_failed(PROVIDER, step, OAuthFailure.BAD_RESPONSE) from None


class GoogleProvider:
    """``AuthProvider`` for Google. One instance per process keeps the caches warm."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        client_factory: ClientFactory,
        clock: Clock = _utcnow,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._client_factory = client_factory
        self._clock = clock
        self._discovery: _Cached[_Discovery] | None = None
        self._jwks: _Cached[jwt.PyJWKSet] | None = None
        self._last_forced_refresh: datetime | None = None

    @property
    def name(self) -> AuthProviderName:
        return AuthProviderName.GOOGLE

    def __repr__(self) -> str:  # never show the client secret
        return f"GoogleProvider(client_id={self._client_id!r})"

    # ------------------------------------------------------------ AuthProvider
    async def authorization_url(self, state: str, nonce: str, code_challenge: str) -> str:
        discovery = await self._discovery_doc()
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "scope": SCOPES,
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": PKCE_METHOD,
                "prompt": ACCOUNT_PROMPT,
            }
        )
        return f"{discovery.authorization_endpoint}?{query}"

    async def complete(self, code: str, code_verifier: str, nonce: str) -> ProviderProfile:
        id_token = await self._exchange_code(code, code_verifier)
        claims = await self._verify_id_token(id_token)
        if not hmac.compare_digest(claims.nonce.encode(), nonce.encode()):
            raise oauth_failed(PROVIDER, OAuthStep.ID_TOKEN, OAuthFailure.NONCE_MISMATCH)
        return ProviderProfile(
            provider=AuthProviderName.GOOGLE,
            subject=claims.sub,
            email=claims.email,
            email_verified=claims.email_verified,
            name=claims.name,
            avatar_url=claims.picture,
        )

    # ---------------------------------------------------------------- network
    async def _fetch(self, step: OAuthStep, request: httpx.Request) -> Any:
        try:
            async with self._client_factory(JSON_HEADERS) as http:
                return await send(http, PROVIDER.value, request)
        except UpstreamError as exc:
            upstream = str((exc.meta or {}).get("reason", ""))
            reason = _UPSTREAM_FAILURES.get(upstream, OAuthFailure.BAD_RESPONSE)
            raise oauth_failed(PROVIDER, step, reason) from None

    async def _discovery_doc(self) -> _Discovery:
        now = self._clock()
        if self._discovery and now - self._discovery.fetched_at < METADATA_TTL:
            return self._discovery.value
        body = await self._fetch(OAuthStep.DISCOVERY, httpx.Request("GET", DISCOVERY_URL))
        discovery = _parse(_Discovery, body, OAuthStep.DISCOVERY)
        self._discovery = _Cached(discovery, now)
        return discovery

    async def _exchange_code(self, code: str, code_verifier: str) -> str:
        discovery = await self._discovery_doc()
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "redirect_uri": self._redirect_uri,
        }
        request = httpx.Request("POST", discovery.token_endpoint, data=form)
        body = await self._fetch(OAuthStep.TOKEN, request)
        return _parse(_TokenResponse, body, OAuthStep.TOKEN).id_token

    # ---------------------------------------------------------------- id_token
    async def _fetch_jwks(self, now: datetime) -> jwt.PyJWKSet:
        discovery = await self._discovery_doc()
        body = await self._fetch(OAuthStep.JWKS, httpx.Request("GET", discovery.jwks_uri))
        try:
            jwks = jwt.PyJWKSet.from_dict(body)
        except (jwt.PyJWKSetError, jwt.InvalidKeyError, TypeError, KeyError):
            raise oauth_failed(PROVIDER, OAuthStep.JWKS, OAuthFailure.BAD_RESPONSE) from None
        self._jwks = _Cached(jwks, now)
        return jwks

    def _may_force_refresh(self, now: datetime) -> bool:
        last = self._last_forced_refresh
        return last is None or now - last >= FORCED_JWKS_REFRESH_INTERVAL

    async def _signing_key(self, kid: str) -> jwt.PyJWK:
        now = self._clock()
        cached = self._jwks
        fresh = cached is not None and now - cached.fetched_at < METADATA_TTL
        jwks = cached.value if cached is not None and fresh else await self._fetch_jwks(now)
        key = _find_key(jwks, kid)
        if key is None and self._may_force_refresh(now):
            self._last_forced_refresh = now
            key = _find_key(await self._fetch_jwks(now), kid)
        if key is None:
            raise oauth_failed(PROVIDER, OAuthStep.ID_TOKEN, OAuthFailure.UNKNOWN_KEY)
        return key

    async def _verify_id_token(self, id_token: str) -> _IdTokenClaims:
        try:
            kid = jwt.get_unverified_header(id_token).get("kid")
        except jwt.InvalidTokenError:
            raise _invalid_id_token() from None
        if not isinstance(kid, str) or not kid:
            raise _invalid_id_token()
        key = await self._signing_key(kid)
        try:
            claims = jwt.decode(
                id_token,
                key=key,
                algorithms=[ID_TOKEN_ALGORITHM],
                audience=self._client_id,
                issuer=ISSUERS,
                leeway=ID_TOKEN_LEEWAY,
                options={"require": ["iss", "aud", "exp", "iat", "sub"]},
            )
            return _IdTokenClaims.model_validate(claims)
        except (jwt.InvalidTokenError, ValidationError):
            raise _invalid_id_token() from None


def _invalid_id_token() -> OAuthFailedError:
    return oauth_failed(PROVIDER, OAuthStep.ID_TOKEN, OAuthFailure.ID_TOKEN_INVALID)


def _find_key(jwks: jwt.PyJWKSet, kid: str) -> jwt.PyJWK | None:
    try:
        return jwks[kid]
    except KeyError:
        return None
