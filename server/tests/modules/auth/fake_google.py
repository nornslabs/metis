"""A fake Google OpenID provider served through ``httpx.MockTransport``.

It answers the discovery document, the token endpoint and the JWKS. The token
endpoint returns an ``id_token`` signed with a test RSA key; tests shape its
claims (``claims``), sign it with another key (``signing_key``), or make the
endpoint fail (``token_status``, ``token_body``, ``network_down``). Every token
request body is recorded in ``token_requests``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

ISSUER = "https://accounts.google.com"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
AUTHORIZATION_URL = f"{ISSUER}/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
RSA_EXPONENT = 65537
RSA_KEY_BITS = 2048

SUBJECT = "google-sub-ada"
EMAIL = "ada@example.com"


def new_rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=RSA_EXPONENT, key_size=RSA_KEY_BITS)


@dataclass
class FakeGoogle:
    client_id: str
    key: rsa.RSAPrivateKey = field(default_factory=new_rsa_key)
    kid: str = "test-key-1"
    # Claim overrides for the next id_token; a ``None`` value removes the claim.
    claims: dict[str, Any] = field(default_factory=dict)
    signing_key: rsa.RSAPrivateKey | None = None
    token_status: int = 200
    token_body: str | None = None
    network_down: bool = False
    nonce: str | None = None
    token_requests: list[dict[str, str]] = field(default_factory=list)
    jwks_fetches: int = 0
    issued_id_tokens: list[str] = field(default_factory=list)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def rotate_key(self, kid: str) -> None:
        """Sign with a new key under a new ``kid`` (Google key rotation)."""
        self.key = new_rsa_key()
        self.kid = kid

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if self.network_down:
            raise httpx.ConnectError("fake network down", request=request)
        url = str(request.url)
        if url == DISCOVERY_URL:
            return httpx.Response(200, json=self._discovery())
        if url == JWKS_URL:
            self.jwks_fetches += 1
            return httpx.Response(200, json=self._jwks())
        if url == TOKEN_URL and request.method == "POST":
            return self._token(request)
        return httpx.Response(404)

    @staticmethod
    def _discovery() -> dict[str, Any]:
        return {
            "issuer": ISSUER,
            "authorization_endpoint": AUTHORIZATION_URL,
            "token_endpoint": TOKEN_URL,
            "jwks_uri": JWKS_URL,
        }

    def _jwks(self) -> dict[str, Any]:
        jwk = RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
        return {"keys": [{**jwk, "kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def _token(self, request: httpx.Request) -> httpx.Response:
        form = dict(httpx.QueryParams(request.content.decode()))
        self.token_requests.append(form)
        if self.token_body is not None:
            return httpx.Response(self.token_status, content=self.token_body)
        if self.token_status != 200:
            return httpx.Response(self.token_status, json={"error": "invalid_grant"})
        id_token = self.id_token()
        self.issued_id_tokens.append(id_token)
        body = {"access_token": "ya29.fake", "id_token": id_token, "token_type": "Bearer"}
        return httpx.Response(200, content=json.dumps(body))

    def id_token(self) -> str:
        now = datetime.now(UTC)
        base: dict[str, Any] = {
            "iss": ISSUER,
            "aud": self.client_id,
            "sub": SUBJECT,
            "email": EMAIL,
            "email_verified": True,
            "name": "Ada Lovelace",
            "picture": "https://lh3.googleusercontent.com/a/ada",
            "iat": now,
            "exp": now + timedelta(hours=1),
            "nonce": self.nonce,
        }
        claims = {k: v for k, v in {**base, **self.claims}.items() if v is not None}
        key = self.signing_key or self.key
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": self.kid})
