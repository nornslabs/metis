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
import json
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
    # What ``list_teams`` and ``list_issue_labels`` answer (JSON text, as Linear's tools do).
    teams: list[dict[str, str]] = field(
        default_factory=lambda: [
            {"id": "team-1", "name": "Product", "key": "PRD"},
            {"id": "team-2", "name": "Platform", "key": "PLT"},
        ]
    )
    label_names: list[str] = field(default_factory=lambda: ["backend", "bug"])
    # What ``save_project`` and ``save_milestone`` created, by Linear id, in creation order.
    projects: dict[str, dict[str, Any]] = field(default_factory=dict)
    milestones: dict[str, dict[str, Any]] = field(default_factory=dict)
    # What ``save_issue`` created, by Linear id (``blocked_by`` only ever grows, as Linear's does),
    # and the labels ``create_issue_label`` made.
    issues: dict[str, dict[str, Any]] = field(default_factory=dict)
    labels_created: list[str] = field(default_factory=list)
    # ``save_issue`` fails (every time) for an issue with one of these titles.
    fail_issue_titles: set[str] = field(default_factory=set)
    # ``create_issue_label`` fails (every time) when set.
    fail_label_create: bool = False
    # After this many write calls the token stops working and cannot be refreshed, so the next
    # call finds the connection expired.
    expire_after_writes: int | None = None
    # Fail the Nth ``save_*`` call (1-based, counted over the fake's life) once, as a provider
    # error, before it changes anything; ``None`` never fails.
    fail_save_at: int | None = None
    # Answer ``save_*`` with text that holds no id.
    save_without_id: bool = False
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
            self._server.add_tool(self._tool_for(name), name=name, description=f"Linear {name}")
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
    def write_calls(self) -> list[str]:
        """Names of the write tools (``save_*``, ``delete_*``) Linear was asked to run."""
        return [
            name
            for name, _ in self.tool_calls
            if name.startswith(("save_", "delete_")) or name == "create_issue_label"
        ]

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

    def _tool_for(self, name: str) -> Any:
        if name == "save_project":
            return self._save_project_tool()
        if name == "save_milestone":
            return self._save_milestone_tool()
        if name == "save_issue":
            return self._save_issue_tool()
        if name == "create_issue_label":
            return self._create_label_tool()
        return self._tool(name)

    def _check_save(self, name: str, arguments: dict[str, Any]) -> None:
        self.tool_calls.append((name, arguments))
        if self.fail_save_at is not None and len(self.write_calls) == self.fail_save_at:
            self.fail_save_at = None
            raise RuntimeError("Linear could not save the item")

    def _answer(self, kind: str, store: dict[str, dict[str, Any]], key: str) -> str:
        if self.save_without_id:
            return "saved"
        item = store[key]
        return json.dumps({"id": key, "url": f"https://linear.app/{kind}/{key}", **item})

    def _save_project_tool(self) -> Any:
        async def save_project(
            name: str = "",
            description: str = "",
            id: str = "",  # noqa: A002 - Linear's argument name
            addTeams: list[str] | None = None,  # noqa: N803
        ) -> str:
            arguments = {"name": name, "description": description, "id": id, "teams": addTeams}
            self._check_save("save_project", arguments)
            if id and id not in self.projects:
                raise RuntimeError("Project not found")
            key = id or f"project-{len(self.projects) + 1}"
            teams = addTeams if addTeams is not None else self.projects.get(key, {}).get("teams")
            self.projects[key] = {"name": name, "description": description, "teams": teams}
            return self._answer("project", self.projects, key)

        return save_project

    def _save_milestone_tool(self) -> Any:
        async def save_milestone(
            project: str = "",
            name: str = "",
            description: str = "",
            sortOrder: int = 0,  # noqa: N803
            id: str = "",  # noqa: A002 - Linear's argument name
        ) -> str:
            arguments = {
                "project": project,
                "name": name,
                "description": description,
                "sort_order": sortOrder,
                "id": id,
            }
            self._check_save("save_milestone", arguments)
            if project not in self.projects or (id and id not in self.milestones):
                raise RuntimeError("Project or milestone not found")
            key = id or f"milestone-{len(self.milestones) + 1}"
            self.milestones[key] = {
                "project": project,
                "name": name,
                "description": description,
                "sort_order": sortOrder,
            }
            return self._answer("milestone", self.milestones, key)

        return save_milestone

    def _save_issue_tool(self) -> Any:
        async def save_issue(
            title: str = "",
            description: str = "",
            team: str = "",
            project: str = "",
            projectMilestone: str = "",  # noqa: N803 - Linear's argument name
            estimate: int = 0,
            labels: list[str] | None = None,
            parentId: str = "",  # noqa: N803
            id: str = "",  # noqa: A002
            blockedBy: list[str] | None = None,  # noqa: N803
        ) -> str:
            arguments = {
                "title": title,
                "description": description,
                "team": team,
                "project": project,
                "milestone": projectMilestone,
                "estimate": estimate,
                "labels": labels,
                "parent": parentId,
                "id": id,
                "blocked_by": blockedBy,
            }
            self._check_save("save_issue", arguments)
            if title in self.fail_issue_titles:
                raise RuntimeError("Linear could not save the issue")
            if id and id not in self.issues:
                raise RuntimeError("Issue not found")
            key = id or f"issue-{len(self.issues) + 1}"
            current = self.issues.get(key, {})
            blocked = sorted(set(current.get("blocked_by", [])) | set(blockedBy or []))
            fields = (
                {
                    "title": title,
                    "description": description,
                    "team": team,
                    "project": project,
                    "milestone": projectMilestone,
                    "estimate": estimate,
                    "labels": labels or [],
                    "parent": parentId,
                }
                if title
                else {}
            )
            self.issues[key] = {**current, **fields, "blocked_by": blocked}
            return self._answer("issue", self.issues, key)

        return save_issue

    def _create_label_tool(self) -> Any:
        async def create_issue_label(name: str = "", team: str = "") -> str:
            self.tool_calls.append(("create_issue_label", {"name": name, "team": team}))
            if self.fail_label_create:
                raise RuntimeError("Linear could not create the label")
            self.labels_created.append(name)
            self.label_names.append(name)
            return json.dumps({"id": f"label-{len(self.label_names)}", "name": name})

        return create_issue_label

    def _tool(self, name: str) -> Any:
        async def tool(query: str = "", title: str = "") -> str:
            self.tool_calls.append((name, {"query": query, "title": title}))
            if name == "list_teams":
                return json.dumps(self.teams)
            if name == "list_issue_labels":
                return json.dumps(
                    [{"id": f"l{i}", "name": n} for i, n in enumerate(self.label_names)]
                )
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
            limit = self._fake.expire_after_writes
            # The lapse is seen at the start of a call (``initialize``), never between the steps
            # of one call, so a write that Linear has made is also answered.
            if (
                limit is not None
                and _is_initialize(request)
                and len(self._fake.write_calls) >= limit
            ):
                self._fake.expire_after_writes = None
                self._fake.revoke_access_tokens()
                self._fake.refresh_status = 400
            if not self._fake._bearer_ok(request):
                return httpx.Response(401)
            if self._fake.transient_failures and b"tools/call" in request.content:
                self._fake.transient_failures -= 1
                return httpx.Response(500)
            if self._fake.mcp_error_status is not None:
                return httpx.Response(self._fake.mcp_error_status)
            return await self._mcp.handle_async_request(request)
        return self._fake._oauth(request)


def _is_initialize(request: httpx.Request) -> bool:
    try:
        body = json.loads(request.content)
    except ValueError:
        return False
    return isinstance(body, dict) and body.get("method") == "initialize"
