"""An in-process stand-in for Linear's OAuth server and hosted MCP server.

One ``httpx`` transport serves both: ``/mcp`` is a real MCP server (``FastMCP``) that answers
only for a valid bearer token; every other path is the OAuth side (protected-resource and
authorization-server metadata, dynamic registration, token with PKCE, revocation). ``mode``
knobs make each step fail. It records what it received so tests can assert on it.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import Receive, Scope, Send

from metis.adapters.mcp.linear import SERVER_URL

MCP_HOST = httpx.URL(SERVER_URL).host
AUTH_ISSUER = "https://auth.linear.test"
AUTH_HOST = httpx.URL(AUTH_ISSUER).host
CLIENT_ID = "metis-client-1"
CLIENT_SECRET = "fake-client-secret-0123456789"
TOOL_NAMES = ("list_issues", "create_issue")
BIG_RESULT_CHARS = 10_000


@dataclass
class FakeLinear:
    """Mutable behaviour switches and request records."""

    access_lifetime_seconds: int = 3600
    issue_client_secret: bool = False
    registration_enabled: bool = True
    token_status: int = 200
    refresh_status: int = 200
    mcp_unauthorized: bool = False
    mcp_error_status: int | None = None
    tools: tuple[str, ...] = TOOL_NAMES
    # Answer the next N ``tools/call`` requests with a 500 (a transient provider failure).
    transient_failures: int = 0
    tool_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    revocation_status: int = 200
    registrations: list[dict[str, Any]] = field(default_factory=list)
    token_requests: list[dict[str, str]] = field(default_factory=list)
    revocations: list[dict[str, str]] = field(default_factory=list)
    mcp_tokens_seen: list[str | None] = field(default_factory=list)
    _challenges: dict[str, str] = field(default_factory=dict)
    _valid_access: set[str] = field(default_factory=set)
    _valid_refresh: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self._server = FastMCP(
            "fake-linear",
            stateless_http=True,
            json_response=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        for name in self.tools:
            self._server.add_tool(self._tool(name), name=name, description=f"Linear {name}")
        self._mcp_app = self._server.streamable_http_app()

    # ------------------------------------------------------------------ test API
    def authorize(self, authorize_url: str) -> str:
        """What the consent screen does: check the request and hand back a one-time code."""
        query = httpx.URL(authorize_url).params
        assert query["response_type"] == "code"
        assert query["code_challenge_method"] == "S256"
        assert query["client_id"] == CLIENT_ID
        assert query["resource"] == SERVER_URL
        code = secrets.token_urlsafe(16)
        self._challenges[code] = query["code_challenge"]
        return code

    def revoke_access_tokens(self) -> None:
        """Make every issued access token stop working (the MCP server answers 401)."""
        self._valid_access.clear()

    @property
    def refresh_count(self) -> int:
        return sum(1 for r in self.token_requests if r["grant_type"] == "refresh_token")

    def transport(self) -> httpx.AsyncBaseTransport:
        return _Transport(self)

    @asynccontextmanager
    async def running(self) -> AsyncGenerator[FakeLinear]:
        """Run the MCP session manager for the test (in its own task, like the Exa fake)."""
        started, stop = asyncio.Event(), asyncio.Event()

        async def serve() -> None:
            async with self._server.session_manager.run():
                started.set()
                await stop.wait()

        task = asyncio.create_task(serve())
        await started.wait()
        try:
            yield self
        finally:
            stop.set()
            await task

    # ---------------------------------------------------------------- internals
    def issue_tokens(self) -> tuple[str, str]:
        """A valid access and refresh token, as a finished sign-in would have stored."""
        access, refresh = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        self._valid_access.add(access)
        self._valid_refresh.add(refresh)
        return access, refresh

    def _tool(self, name: str) -> Any:
        async def tool(query: str = "", title: str = "") -> str:
            self.tool_calls.append((name, {"query": query, "title": title}))
            return "x" * BIG_RESULT_CHARS if name == "big_result" else name

        tool.__name__ = name
        return tool

    def _oauth(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.host == MCP_HOST and path.startswith(
            "/.well-known/oauth-protected-resource"
        ):
            return httpx.Response(200, json={"authorization_servers": [AUTH_ISSUER]})
        if request.url.host == AUTH_HOST and path == "/.well-known/oauth-authorization-server":
            return httpx.Response(200, json=self._metadata())
        if request.url.host == AUTH_HOST and path == "/register":
            return self._register(request)
        if request.url.host == AUTH_HOST and path == "/token":
            return self._token(request)
        if request.url.host == AUTH_HOST and path == "/revoke":
            self.revocations.append(dict(httpx.QueryParams(request.content.decode())))
            return httpx.Response(self.revocation_status)
        return httpx.Response(404)

    def _metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "issuer": AUTH_ISSUER,
            "authorization_endpoint": f"{AUTH_ISSUER}/authorize",
            "token_endpoint": f"{AUTH_ISSUER}/token",
            "revocation_endpoint": f"{AUTH_ISSUER}/revoke",
            "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
        }
        if self.registration_enabled:
            metadata["registration_endpoint"] = f"{AUTH_ISSUER}/register"
        return metadata

    def _register(self, request: httpx.Request) -> httpx.Response:
        import json

        self.registrations.append(json.loads(request.content))
        body: dict[str, Any] = {"client_id": CLIENT_ID}
        if self.issue_client_secret:
            body["client_secret"] = CLIENT_SECRET
        return httpx.Response(201, json=body)

    def _token(self, request: httpx.Request) -> httpx.Response:
        form = dict(httpx.QueryParams(request.content.decode()))
        self.token_requests.append(form)
        refreshing = form["grant_type"] == "refresh_token"
        status = self.refresh_status if refreshing else self.token_status
        if status != 200:
            return httpx.Response(status, json={"error": "invalid_grant"})
        if refreshing:
            if form.get("refresh_token") not in self._valid_refresh:
                return httpx.Response(400, json={"error": "invalid_grant"})
            self._valid_refresh.discard(form["refresh_token"])
        else:
            challenge = self._challenges.pop(form.get("code", ""), None)
            verifier = form.get("code_verifier", "")
            digest = hashlib.sha256(verifier.encode()).digest()
            expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
            if challenge is None or challenge != expected:
                return httpx.Response(400, json={"error": "invalid_grant"})
        access, refresh = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        self._valid_access.add(access)
        self._valid_refresh.add(refresh)
        return httpx.Response(
            200,
            json={
                "access_token": access,
                "token_type": "Bearer",
                "refresh_token": refresh,
                "expires_in": self.access_lifetime_seconds,
                "scope": "read write",
            },
        )

    def _bearer_ok(self, request: httpx.Request) -> bool:
        header = request.headers.get("authorization", "")
        token = header.removeprefix("Bearer ") if header.startswith("Bearer ") else None
        self.mcp_tokens_seen.append(token)
        return not self.mcp_unauthorized and token in self._valid_access

    async def _asgi(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._mcp_app(scope, receive, send)


class _Transport(httpx.AsyncBaseTransport):
    def __init__(self, fake: FakeLinear) -> None:
        self._fake = fake
        self._mcp = httpx.ASGITransport(app=fake._asgi)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == MCP_HOST and request.url.path == httpx.URL(SERVER_URL).path:
            if not self._fake._bearer_ok(request):
                return httpx.Response(401)
            if self._fake.transient_failures and b"tools/call" in request.content:
                self._fake.transient_failures -= 1
                return httpx.Response(500)
            if self._fake.mcp_error_status is not None:
                return httpx.Response(self._fake.mcp_error_status)
            return await self._mcp.handle_async_request(request)
        return self._fake._oauth(request)
