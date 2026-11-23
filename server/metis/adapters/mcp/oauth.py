"""OAuth 2.1 for remote MCP servers: discovery, dynamic client registration, PKCE tokens.

Follows the MCP authorization flow with ``httpx`` only: the server's protected-resource
metadata (RFC 9728) names its authorization server, whose metadata (RFC 8414) gives the
endpoints; a public client is registered on the fly (RFC 7591) and the authorization code is
exchanged with PKCE (``S256``) and the ``resource`` parameter (RFC 8707).

Every function takes a ``ClientFactory`` (tests route it to fakes). Failures become
``UpstreamError`` with a safe reason; codes, tokens, client secrets and upstream bodies never
reach an error or a log.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from metis.core.config import get_settings
from metis.core.errors import UpstreamError
from metis.core.logging import get_logger
from metis.helpers.http import ClientFactory, FailureReason, capped, provider_error, send

CLIENT_NAME = "Metis"
WELL_KNOWN = "/.well-known"
PROTECTED_RESOURCE_PATH = f"{WELL_KNOWN}/oauth-protected-resource"
AUTH_SERVER_PATH = f"{WELL_KNOWN}/oauth-authorization-server"
OPENID_PATH = f"{WELL_KNOWN}/openid-configuration"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
NO_AUTH_METHOD = "none"

logger = get_logger(__name__)


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class AuthServerMetadata(_Model):
    """The authorization server's endpoints (RFC 8414)."""

    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None = None
    revocation_endpoint: str | None = None
    scopes_supported: list[str] = Field(default_factory=list)
    token_endpoint_auth_methods_supported: list[str] = Field(default_factory=list)


class RegisteredClient(_Model):
    """The OAuth client registered for one connection (``client_secret`` only if issued)."""

    client_id: str
    client_secret: SecretStr | None = None


class TokenSet(_Model):
    """A token answer; ``expires_at`` is ``None`` when the server sent no lifetime."""

    access_token: SecretStr
    refresh_token: SecretStr | None = None
    expires_at: datetime | None = None
    scopes: list[str] = Field(default_factory=list)


class _TokenAnswer(_Model):
    access_token: str = Field(min_length=1)
    token_type: str = "Bearer"
    refresh_token: str | None = None
    expires_in: int | None = Field(default=None, gt=0)
    scope: str | None = None


class _ProtectedResource(_Model):
    authorization_servers: list[str] = Field(default_factory=list)


async def discover(
    make_client: ClientFactory, provider: str, server_url: str
) -> AuthServerMetadata:
    """Find the authorization server of the MCP server at ``server_url``.

    Raises ``UpstreamError`` (``not_supported``) when no usable metadata is published.
    """
    async with capped(provider), make_client({}) as http:
        issuer = await _issuer_of(http, provider, server_url)
        raw = await _first_json(http, provider, _metadata_urls(issuer))
    try:
        metadata = AuthServerMetadata.model_validate(raw)
    except ValidationError:
        raise provider_error(provider, FailureReason.NOT_SUPPORTED) from None
    for endpoint in (
        metadata.authorization_endpoint,
        metadata.token_endpoint,
        metadata.registration_endpoint,
        metadata.revocation_endpoint,
    ):
        if endpoint is not None:
            _require_secure(provider, endpoint)
    return metadata


async def register_client(
    make_client: ClientFactory, provider: str, metadata: AuthServerMetadata, redirect_uri: str
) -> RegisteredClient:
    """Register a public client by dynamic registration; ``not_supported`` if offered none."""
    if metadata.registration_endpoint is None:
        raise provider_error(provider, FailureReason.NOT_SUPPORTED)
    methods = metadata.token_endpoint_auth_methods_supported
    if methods and NO_AUTH_METHOD not in methods:
        raise provider_error(provider, FailureReason.NOT_SUPPORTED)  # public clients only
    body = {
        "client_name": CLIENT_NAME,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": NO_AUTH_METHOD,
    }
    request = httpx.Request("POST", metadata.registration_endpoint, json=body)
    async with make_client({}) as http:
        answer = await send(http, provider, request)
    return _parse(RegisteredClient, answer, provider)


def authorization_url(
    metadata: AuthServerMetadata,
    client: RegisteredClient,
    *,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    resource: str,
    scopes: list[str],
) -> str:
    """The URL that sends the browser to the provider's consent screen."""
    query = {
        "response_type": "code",
        "client_id": client.client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "resource": resource,
    }
    if scopes:
        query["scope"] = " ".join(scopes)
    separator = "&" if urlsplit(metadata.authorization_endpoint).query else "?"
    return f"{metadata.authorization_endpoint}{separator}{urlencode(query)}"


async def exchange_code(
    make_client: ClientFactory,
    provider: str,
    *,
    token_endpoint: str,
    client: RegisteredClient,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    resource: str,
) -> TokenSet:
    """Trade the authorization ``code`` for tokens."""
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
        "resource": resource,
    }
    return await _token_request(make_client, provider, token_endpoint, client, form)


async def refresh(
    make_client: ClientFactory,
    provider: str,
    *,
    token_endpoint: str,
    client: RegisteredClient,
    refresh_token: str,
    resource: str,
) -> TokenSet:
    """Trade a refresh token for a new token set (the old refresh token may stop working)."""
    form = {"grant_type": "refresh_token", "refresh_token": refresh_token, "resource": resource}
    return await _token_request(make_client, provider, token_endpoint, client, form)


async def revoke(
    make_client: ClientFactory,
    provider: str,
    *,
    revocation_endpoint: str,
    client: RegisteredClient,
    token: str,
) -> None:
    """Tell the provider to drop ``token``. Best effort: a failure is logged and ignored."""
    form = {"token": token, "client_id": client.client_id}
    if client.client_secret is not None:
        form["client_secret"] = client.client_secret.get_secret_value()
    request = httpx.Request("POST", revocation_endpoint, data=form)
    try:
        async with make_client({}) as http:
            await send(http, provider, request)
    except UpstreamError as exc:
        logger.warning("mcp_oauth.revoke_failed", provider=provider, reason=reason_of(exc))


async def _token_request(
    make_client: ClientFactory,
    provider: str,
    token_endpoint: str,
    client: RegisteredClient,
    form: dict[str, str],
) -> TokenSet:
    _require_secure(provider, token_endpoint)
    body = {**form, "client_id": client.client_id}
    if client.client_secret is not None:
        body["client_secret"] = client.client_secret.get_secret_value()
    request = httpx.Request("POST", token_endpoint, data=body)
    async with make_client({}) as http:
        answer = _parse(_TokenAnswer, await send(http, provider, request), provider)
    if answer.token_type.lower() != "bearer":
        raise provider_error(provider, FailureReason.BAD_RESPONSE)
    expires_at = (
        datetime.now(UTC) + timedelta(seconds=answer.expires_in) if answer.expires_in else None
    )
    return TokenSet(
        access_token=SecretStr(answer.access_token),
        refresh_token=SecretStr(answer.refresh_token) if answer.refresh_token else None,
        expires_at=expires_at,
        scopes=answer.scope.split() if answer.scope else [],
    )


async def _issuer_of(http: httpx.AsyncClient, provider: str, server_url: str) -> str:
    """The authorization server named by the MCP server, or the MCP server's own origin."""
    parts = urlsplit(server_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    path = parts.path.rstrip("/")
    candidates = [f"{origin}{PROTECTED_RESOURCE_PATH}{path}", f"{origin}{PROTECTED_RESOURCE_PATH}"]
    raw = await _first_json(http, provider, candidates, required=False)
    if raw is not None:
        try:
            servers = _ProtectedResource.model_validate(raw).authorization_servers
        except ValidationError:
            servers = []
        if servers:
            return servers[0]
    return origin


def _metadata_urls(issuer: str) -> list[str]:
    parts = urlsplit(issuer)
    origin = f"{parts.scheme}://{parts.netloc}"
    path = parts.path.rstrip("/")
    urls = [f"{origin}{AUTH_SERVER_PATH}{path}", f"{origin}{OPENID_PATH}{path}"]
    if path:
        urls.append(f"{issuer.rstrip('/')}{OPENID_PATH}")
    return urls


async def _first_json(
    http: httpx.AsyncClient, provider: str, urls: list[str], *, required: bool = True
) -> Any:
    """The first URL that answers with JSON; ``None`` (or ``not_supported``) if none does."""
    for url in urls:
        _require_secure(provider, url)
        try:
            return await send(http, provider, httpx.Request("GET", url))
        except UpstreamError as exc:
            if reason_of(exc) in {FailureReason.TIMEOUT.value, FailureReason.UNREACHABLE.value}:
                raise
    if required:
        raise provider_error(provider, FailureReason.NOT_SUPPORTED)
    return None


def _require_secure(provider: str, url: str) -> None:
    """Refuse to talk to a plain-HTTP endpoint (``localhost`` is allowed in development)."""
    parts = urlsplit(url)
    local_dev = get_settings().is_development and parts.hostname in LOCAL_HOSTS
    if parts.scheme != "https" and not (parts.scheme == "http" and local_dev):
        raise provider_error(provider, FailureReason.NOT_SUPPORTED)


def _parse[ModelT: BaseModel](model: type[ModelT], raw: Any, provider: str) -> ModelT:
    try:
        return model.model_validate(raw)
    except ValidationError:
        raise provider_error(provider, FailureReason.BAD_RESPONSE) from None


def reason_of(exc: UpstreamError) -> str:
    """The safe failure reason carried by an adapter error."""
    meta = exc.meta or {}
    return str(meta.get("reason", FailureReason.BAD_RESPONSE.value))
