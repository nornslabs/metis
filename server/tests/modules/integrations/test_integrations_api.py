"""MCP connections with OAuth and tool discovery (SHIP-231).

Seam: HTTP requests against the real FastAPI app as the non-superuser ``metis_app`` role
(see ``tests/modules/conftest.py``), with real Postgres and Redis. Linear's OAuth server and
hosted MCP server are an in-process fake (``fake_linear.py``) reached through the overridden
``provider_http_factory``; nothing leaves the process.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from metis.core.errors import SecretDecryptError
from metis.entrypoints.api import app
from metis.helpers.http import ClientFactory, provider_http_factory
from metis.modules import integrations
from metis.modules.integrations.helpers import sealing
from tests.helpers.auth import APP_ROLE, SESSION_COOKIE, assert_problem, auth, sign_in
from tests.helpers.fake_linear import CLIENT_ID, CLIENT_SECRET, FakeLinear

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

WEB = "http://localhost:3000"
CALLBACK = "/v1/integrations/linear/callback"
SETTINGS_PATH = "/?settings=integrations"
ADA = {"sub": "google-ada", "email": "ada@example.com"}
GRACE = {"sub": "google-grace", "email": "grace@example.com", "name": "Grace"}


# -------------------------------------------------------------------- fixtures
@pytest_asyncio.fixture
async def linear(client: httpx.AsyncClient) -> AsyncIterator[FakeLinear]:
    async with FakeLinear().running() as fake:
        transport = fake.transport()

        def fake_factory() -> ClientFactory:
            return lambda headers: httpx.AsyncClient(transport=transport, headers=dict(headers))

        app.dependency_overrides[provider_http_factory] = fake_factory
        yield fake
        app.dependency_overrides.pop(provider_http_factory, None)


# --------------------------------------------------------------------- helpers
async def start(
    client: httpx.AsyncClient, token: str, workspace: str | None = None, **body: Any
) -> httpx.Response:
    return await client.post(
        "/v1/integrations/linear/connect", json=body, headers=auth(token, workspace)
    )


def state_of(authorize_url: str) -> str:
    return parse_qs(urlsplit(authorize_url).query)["state"][0]


async def callback(
    client: httpx.AsyncClient, token: str | None, **params: str | None
) -> httpx.Response:
    headers = {"Cookie": f"{SESSION_COOKIE}={token}"} if token else {}
    query = {key: value for key, value in params.items() if value is not None}
    return await client.get(CALLBACK, params=query, headers=headers)


async def connect(
    client: httpx.AsyncClient, linear: FakeLinear, token: str, workspace: str | None = None
) -> httpx.Response:
    """The whole round trip; returns the callback's redirect."""
    started = await start(client, token, workspace)
    assert started.status_code == 200, started.text
    url = started.json()["authorize_url"]
    return await callback(client, token, code=linear.authorize(url), state=state_of(url))


async def status_of(client: httpx.AsyncClient, token: str, workspace: str | None = None) -> Any:
    response = await client.get("/v1/integrations", headers=auth(token, workspace))
    assert response.status_code == 200, response.text
    (linear_entry,) = [i for i in response.json()["items"] if i["provider"] == "linear"]
    return linear_entry


async def workspace_id_of(client: httpx.AsyncClient, token: str) -> str:
    response = await client.get("/v1/workspaces/current", headers=auth(token))
    return str(response.json()["workspace"]["id"])


async def add_member(engine: AsyncEngine, workspace_id: str, token_user: str) -> None:
    async with engine.begin() as conn:
        user_id = await conn.scalar(
            text("SELECT id FROM auth.users WHERE email = :email"), {"email": token_user}
        )
        await conn.execute(
            text(
                "INSERT INTO identity.members (workspace_id, user_id, role) "
                "VALUES (:ws, :user, 'member')"
            ),
            {"ws": workspace_id, "user": user_id},
        )


async def stored_row(engine: AsyncEngine, workspace_id: str) -> Any:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT status, sealed_tokens, scopes, expires_at, version "
                "FROM integrations.mcp_connections WHERE workspace_id = :ws"
            ),
            {"ws": workspace_id},
        )
        return result.mappings().first()


async def expire_in_db(engine: AsyncEngine, workspace_id: str, seconds: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE integrations.mcp_connections "
                "SET expires_at = now() + make_interval(secs => :s) WHERE workspace_id = :ws"
            ),
            {"ws": workspace_id, "s": seconds},
        )


def assert_redirect(response: httpx.Response, path: str, **params: str) -> None:
    assert response.status_code == 302, response.text
    location = urlsplit(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}" == WEB
    assert location.path == urlsplit(path).path
    query = {k: v[0] for k, v in parse_qs(location.query).items()}
    for key, value in params.items():
        assert query.get(key) == value, location.query


# --------------------------------------------------------------------- connect
async def test_connect_round_trip_stores_a_connected_row_and_lists_tools(
    client: httpx.AsyncClient, engine: AsyncEngine, redis: Redis, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    started = await start(client, token)
    assert started.status_code == 200, started.text
    url = started.json()["authorize_url"]
    query = parse_qs(urlsplit(url).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["resource"] == ["https://mcp.linear.app/mcp"]
    assert query["redirect_uri"] == [f"{WEB}{CALLBACK}"]
    key = f"integrations:oauth:{state_of(url)}"
    assert 0 < await redis.ttl(key) <= 600
    assert linear.registrations[0]["token_endpoint_auth_method"] == "none"

    redirect = await callback(client, token, code=linear.authorize(url), state=state_of(url))

    assert_redirect(redirect, SETTINGS_PATH, integration="linear")
    assert await redis.exists(key) == 0
    entry = await status_of(client, token)
    assert entry["status"] == "connected"
    assert entry["scopes"] == ["read", "write"]
    assert entry["expires_at"] is not None
    tools = await client.get("/v1/integrations/linear/tools", headers=auth(token))
    assert tools.status_code == 200, tools.text
    assert [t["name"] for t in tools.json()["items"]] == ["list_issues", "create_issue"]


async def test_connect_keeps_the_requested_redirect(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    started = await start(client, token, redirect_to="/ideas/1?panel=plan")
    url = started.json()["authorize_url"]

    redirect = await callback(client, token, code=linear.authorize(url), state=state_of(url))

    assert_redirect(redirect, "/ideas/1", integration="linear", panel="plan")


async def test_an_unsafe_redirect_falls_back_to_the_root(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    started = await start(client, token, redirect_to="https://evil.example/")
    url = started.json()["authorize_url"]

    redirect = await callback(client, token, code=linear.authorize(url), state=state_of(url))

    assert_redirect(redirect, "/", integration="linear")


async def test_a_client_secret_is_sent_to_the_token_endpoint_but_never_stored_plain(
    client: httpx.AsyncClient, engine: AsyncEngine, redis: Redis, linear: FakeLinear
) -> None:
    linear.issue_client_secret = True
    token = await sign_in(engine)
    started = await start(client, token)
    url = started.json()["authorize_url"]

    stored_in_redis = (await redis.get(f"integrations:oauth:{state_of(url)}")) or b""
    await callback(client, token, code=linear.authorize(url), state=state_of(url))

    assert CLIENT_SECRET.encode() not in stored_in_redis
    assert linear.token_requests[0]["client_secret"] == CLIENT_SECRET
    row = await stored_row(engine, await workspace_id_of(client, token))
    assert CLIENT_SECRET not in str(row["sealed_tokens"])


# ---------------------------------------------------------------------- secrets
async def test_tokens_are_sealed_for_their_workspace_and_never_returned(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    workspace = await workspace_id_of(client, token)
    await connect(client, linear, token)

    listed = await client.get("/v1/integrations", headers=auth(token))
    tools = await client.get("/v1/integrations/linear/tools", headers=auth(token))
    row = await stored_row(engine, workspace)

    issued = linear.mcp_tokens_seen[-1]
    assert issued is not None
    for body in (listed.text, tools.text, str(row["sealed_tokens"])):
        assert issued not in body
    opened = sealing.open_tokens(row["sealed_tokens"], UUID(workspace))
    assert opened.access_token.get_secret_value() == issued
    assert opened.client_id == CLIENT_ID
    try:
        sealing.open_tokens(row["sealed_tokens"], UUID(int=1))
    except SecretDecryptError:
        pass
    else:
        raise AssertionError("a sealed connection opened in another workspace")


# ------------------------------------------------------------------ state errors
async def test_a_reused_state_is_refused(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    url = (await start(client, token)).json()["authorize_url"]
    code, state = linear.authorize(url), state_of(url)
    await callback(client, token, code=code, state=state)

    again = await callback(client, token, code=code, state=state)

    assert_redirect(again, SETTINGS_PATH, integration_error="mcp.oauth_state_invalid")
    assert (await status_of(client, token))["version"] == 1


async def test_unknown_missing_and_corrupt_states_are_refused(
    client: httpx.AsyncClient, engine: AsyncEngine, redis: Redis
) -> None:
    token = await sign_in(engine)
    await redis.set("integrations:oauth:corrupt", "not json", ex=60)

    for state in ("never-issued", None, "corrupt"):
        response = await callback(client, token, code="c", state=state)
        assert_redirect(response, SETTINGS_PATH, integration_error="mcp.oauth_state_invalid")
    assert (await status_of(client, token))["status"] == "not_connected"


async def test_another_signed_in_user_cannot_finish_my_connect(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    ada = await sign_in(engine, **ADA)
    grace = await sign_in(engine, **GRACE)
    url = (await start(client, ada)).json()["authorize_url"]

    response = await callback(client, grace, code=linear.authorize(url), state=state_of(url))

    assert_redirect(response, SETTINGS_PATH, integration_error="mcp.oauth_state_invalid")
    assert (await status_of(client, ada))["status"] == "not_connected"
    assert (await status_of(client, grace))["status"] == "not_connected"


async def test_a_user_who_lost_ownership_cannot_finish(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine, **ADA)
    workspace = await workspace_id_of(client, token)
    url = (await start(client, token)).json()["authorize_url"]
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE identity.members SET role = 'member' WHERE workspace_id = :ws"),
            {"ws": workspace},
        )

    response = await callback(client, token, code=linear.authorize(url), state=state_of(url))

    assert_redirect(response, SETTINGS_PATH, integration_error="mcp.oauth_state_invalid")
    assert await stored_row(engine, workspace) is None


async def test_a_callback_without_a_session_goes_to_sign_in(
    client: httpx.AsyncClient, linear: FakeLinear
) -> None:
    response = await callback(client, None, code="c", state="s")

    assert_redirect(response, "/sign-in")


async def test_provider_failures_become_oauth_failed_and_store_nothing(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    workspace = await workspace_id_of(client, token)

    denied = (await start(client, token)).json()["authorize_url"]
    refused = await callback(client, token, error="access_denied", state=state_of(denied))
    assert_redirect(refused, SETTINGS_PATH, integration_error="mcp.oauth_failed")

    broken = (await start(client, token)).json()["authorize_url"]
    linear.token_status = 500
    failed = await callback(client, token, code=linear.authorize(broken), state=state_of(broken))
    assert_redirect(failed, SETTINGS_PATH, integration_error="mcp.oauth_failed")

    linear.registration_enabled = False
    unsupported = await start(client, token)
    assert_problem(unsupported, 502, "mcp.oauth_failed")
    assert await stored_row(engine, workspace) is None


async def test_a_wrong_pkce_verifier_is_refused_by_the_provider(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    url = (await start(client, token)).json()["authorize_url"]
    other = (await start(client, token)).json()["authorize_url"]

    response = await callback(client, token, code=linear.authorize(other), state=state_of(url))

    assert_redirect(response, SETTINGS_PATH, integration_error="mcp.oauth_failed")


# ------------------------------------------------------------------------ access
async def test_members_read_but_only_owners_connect_and_disconnect(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    owner = await sign_in(engine, **ADA)
    workspace = await workspace_id_of(client, owner)
    await connect(client, linear, owner)
    member = await sign_in(engine, **GRACE)
    await add_member(engine, workspace, GRACE["email"])

    assert_problem(await start(client, member, workspace), 403, "auth.forbidden")
    deleted = await client.delete("/v1/integrations/linear", headers=auth(member, workspace))
    assert_problem(deleted, 403, "auth.forbidden")
    assert (await status_of(client, member, workspace))["status"] == "connected"
    tools = await client.get("/v1/integrations/linear/tools", headers=auth(member, workspace))
    assert tools.status_code == 200, tools.text


async def test_another_workspace_sees_nothing_and_cannot_list_tools(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    ada = await sign_in(engine, **ADA)
    await connect(client, linear, ada)
    grace = await sign_in(engine, **GRACE)

    assert (await status_of(client, grace))["status"] == "not_connected"
    tools = await client.get("/v1/integrations/linear/tools", headers=auth(grace))
    assert_problem(tools, 409, "mcp.not_connected")


async def test_routes_need_a_session(client: httpx.AsyncClient) -> None:
    assert_problem(await client.get("/v1/integrations"), 401, "auth.not_signed_in")


async def test_notion_is_not_available_yet(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)

    connect_response = await client.post(
        "/v1/integrations/notion/connect", json={}, headers=auth(token)
    )
    tools = await client.get("/v1/integrations/notion/tools", headers=auth(token))
    unknown = await client.get("/v1/integrations/jira/tools", headers=auth(token))

    assert_problem(connect_response, 422, "mcp.provider_unsupported")
    assert_problem(tools, 422, "mcp.provider_unsupported")
    assert unknown.status_code == 422
    listed = await client.get("/v1/integrations", headers=auth(token))
    assert [i["provider"] for i in listed.json()["items"]] == ["linear"]


# ------------------------------------------------------------------------ refresh
async def test_a_token_close_to_expiry_is_refreshed_before_use(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    workspace = await workspace_id_of(client, token)
    await connect(client, linear, token)
    first = linear.mcp_tokens_seen[-1]
    await expire_in_db(engine, workspace, 30)

    tools = await client.get("/v1/integrations/linear/tools", headers=auth(token))

    assert tools.status_code == 200, tools.text
    assert linear.refresh_count == 1
    assert linear.mcp_tokens_seen[-1] not in (None, first)
    row = await stored_row(engine, workspace)
    assert row["expires_at"] > datetime.now(UTC)
    assert row["version"] == 2


async def test_a_fresh_token_is_not_refreshed(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    await connect(client, linear, token)

    await client.get("/v1/integrations/linear/tools", headers=auth(token))

    assert linear.refresh_count == 0


async def test_two_simultaneous_uses_refresh_once(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    workspace = await workspace_id_of(client, token)
    await connect(client, linear, token)
    await expire_in_db(engine, workspace, 10)

    responses = await asyncio.gather(
        *(client.get("/v1/integrations/linear/tools", headers=auth(token)) for _ in range(2))
    )

    assert [r.status_code for r in responses] == [200, 200]
    assert linear.refresh_count == 1


async def test_a_rejected_refresh_marks_the_connection_expired_until_reconnected(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    workspace = await workspace_id_of(client, token)
    await connect(client, linear, token)
    await expire_in_db(engine, workspace, 5)
    linear.refresh_status = 400

    tools = await client.get("/v1/integrations/linear/tools", headers=auth(token))

    assert_problem(tools, 409, "mcp.expired")
    assert (await status_of(client, token))["status"] == "expired"
    again = await client.get("/v1/integrations/linear/tools", headers=auth(token))
    assert_problem(again, 409, "mcp.expired")

    linear.refresh_status = 200
    assert_redirect(await connect(client, linear, token), SETTINGS_PATH, integration="linear")
    assert (await status_of(client, token))["status"] == "connected"


async def test_a_transient_refresh_failure_does_not_expire_the_connection(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    workspace = await workspace_id_of(client, token)
    await connect(client, linear, token)
    await expire_in_db(engine, workspace, 5)
    linear.refresh_status = 503

    tools = await client.get("/v1/integrations/linear/tools", headers=auth(token))

    assert_problem(tools, 502, "provider.upstream_error")
    assert (await status_of(client, token))["status"] == "connected"


async def test_a_401_from_the_server_refreshes_once_then_expires(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    await connect(client, linear, token)

    linear.revoke_access_tokens()
    recovered = await client.get("/v1/integrations/linear/tools", headers=auth(token))
    assert recovered.status_code == 200, recovered.text
    assert linear.refresh_count == 1

    linear.mcp_unauthorized = True
    expired = await client.get("/v1/integrations/linear/tools", headers=auth(token))
    assert_problem(expired, 409, "mcp.expired")
    assert (await status_of(client, token))["status"] == "expired"


# --------------------------------------------------------------------- disconnect
async def test_disconnect_wipes_the_tokens_and_allows_reconnecting(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    workspace = await workspace_id_of(client, token)
    await connect(client, linear, token)

    deleted = await client.delete("/v1/integrations/linear", headers=auth(token))

    assert deleted.status_code == 204, deleted.text
    assert len(linear.revocations) == 1
    row = await stored_row(engine, workspace)
    assert row["status"] == "revoked"
    assert row["sealed_tokens"] is None
    assert (await status_of(client, token))["status"] == "not_connected"
    tools = await client.get("/v1/integrations/linear/tools", headers=auth(token))
    assert_problem(tools, 409, "mcp.not_connected")
    again = await client.delete("/v1/integrations/linear", headers=auth(token))
    assert_problem(again, 404, "mcp.not_found")
    assert_redirect(await connect(client, linear, token), SETTINGS_PATH, integration="linear")
    assert (await status_of(client, token))["status"] == "connected"


async def test_a_failing_revocation_still_disconnects(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    await connect(client, linear, token)
    linear.revocation_status = 500

    deleted = await client.delete("/v1/integrations/linear", headers=auth(token))

    assert deleted.status_code == 204, deleted.text
    assert (await status_of(client, token))["status"] == "not_connected"


async def test_disconnecting_something_never_connected_is_a_404(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)

    response = await client.delete("/v1/integrations/linear", headers=auth(token))

    assert_problem(response, 404, "mcp.not_found")


# ----------------------------------------------------------------- agent client
async def test_get_mcp_client_loads_tools_with_a_fresh_bearer_token(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    linear: FakeLinear,
) -> None:
    token = await sign_in(engine)
    workspace = await workspace_id_of(client, token)
    await connect(client, linear, token)
    await expire_in_db(engine, workspace, 5)
    transport = linear.transport()

    def make_client(headers: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, headers=dict(headers))

    def mcp_http_client(
        headers: dict[str, str] | None = None, timeout: Any = None, auth: Any = None
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, headers=headers or {})

    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        mcp = await integrations.get_mcp_client(
            session,
            make_client,
            UUID(workspace),
            [integrations.IntegrationProvider.LINEAR],
            httpx_client_factory=mcp_http_client,
        )
        await session.commit()
    tools = await mcp.get_tools()

    assert sorted(t.name for t in tools) == ["create_issue", "list_issues"]
    assert linear.refresh_count == 1


async def test_get_mcp_client_names_the_provider_that_is_not_usable(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    workspace = await workspace_id_of(client, token)

    def make_client(headers: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=linear.transport(), headers=dict(headers))

    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        try:
            await integrations.get_mcp_client(
                session,
                make_client,
                UUID(workspace),
                [integrations.IntegrationProvider.LINEAR],
            )
        except Exception as exc:
            assert getattr(exc, "code", None) is not None
            assert exc.meta == {"provider": "linear"}  # type: ignore[attr-defined]
            assert exc.code.value == "mcp.not_connected"  # type: ignore[attr-defined]
        else:
            raise AssertionError("a missing connection must not give a client")


async def test_the_notion_callback_redirects_with_provider_unsupported(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)

    response = await client.get(
        "/v1/integrations/notion/callback",
        params={"code": "c", "state": "s"},
        headers={"Cookie": f"{SESSION_COOKIE}={token}"},
    )

    assert_redirect(response, SETTINGS_PATH, integration_error="mcp.provider_unsupported")


async def test_a_refresh_survives_a_later_upstream_failure(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    workspace = await workspace_id_of(client, token)
    await connect(client, linear, token)
    await expire_in_db(engine, workspace, 5)
    linear.mcp_error_status = 503

    failed = await client.get("/v1/integrations/linear/tools", headers=auth(token))

    assert_problem(failed, 502, "provider.upstream_error")
    assert linear.refresh_count == 1
    assert (await stored_row(engine, workspace))["version"] == 2  # the new tokens committed
    linear.mcp_error_status = None
    recovered = await client.get("/v1/integrations/linear/tools", headers=auth(token))
    assert recovered.status_code == 200, recovered.text
    assert linear.refresh_count == 1  # the stored token is the new one and is still fresh


async def test_a_connection_with_unreadable_tokens_can_still_be_disconnected(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    workspace = await workspace_id_of(client, token)
    await connect(client, linear, token)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE integrations.mcp_connections SET sealed_tokens = '{}'::jsonb "
                "WHERE workspace_id = :ws"
            ),
            {"ws": workspace},
        )

    deleted = await client.delete("/v1/integrations/linear", headers=auth(token))

    assert deleted.status_code == 204, deleted.text
    assert linear.revocations == []
    assert (await status_of(client, token))["status"] == "not_connected"


# ------------------------------------------------- refresh and expire (agent tools)
async def _in_app_session(engine: AsyncEngine) -> AsyncSession:
    session = AsyncSession(engine, expire_on_commit=False)
    await session.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
    return session


def _make_client(linear: FakeLinear) -> ClientFactory:
    transport = linear.transport()
    return lambda headers: httpx.AsyncClient(transport=transport, headers=dict(headers))


async def test_expire_connection_marks_a_live_connection_expired_once(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    workspace = await workspace_id_of(client, token)
    await connect(client, linear, token)
    provider = integrations.IntegrationProvider.LINEAR

    for _ in range(2):  # the second call changes nothing
        async with await _in_app_session(engine) as session:
            error = await integrations.expire_connection(session, UUID(workspace), provider)
            await session.commit()

    assert error.meta == {"provider": "linear"}
    row = await stored_row(engine, workspace)
    assert (row["status"], row["version"]) == ("expired", 2)
    assert (await status_of(client, token))["status"] == "expired"


async def test_expire_connection_leaves_a_disconnected_connection_alone(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    workspace = await workspace_id_of(client, token)
    await connect(client, linear, token)
    await client.delete("/v1/integrations/linear", headers=auth(token))

    async with await _in_app_session(engine) as session:
        await integrations.expire_connection(
            session, UUID(workspace), integrations.IntegrationProvider.LINEAR
        )
        await session.commit()

    assert (await stored_row(engine, workspace))["status"] == "revoked"


async def test_refresh_connection_replaces_the_tokens_even_when_they_are_fresh(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    workspace = await workspace_id_of(client, token)
    await connect(client, linear, token)

    async with await _in_app_session(engine) as session:
        await integrations.refresh_connection(
            session, _make_client(linear), UUID(workspace), integrations.IntegrationProvider.LINEAR
        )
        await session.commit()

    assert linear.refresh_count == 1
    assert (await stored_row(engine, workspace))["version"] == 2
    assert (await status_of(client, token))["status"] == "connected"


async def test_a_refresh_the_provider_rejects_expires_the_connection(
    client: httpx.AsyncClient, engine: AsyncEngine, linear: FakeLinear
) -> None:
    token = await sign_in(engine)
    workspace = await workspace_id_of(client, token)
    await connect(client, linear, token)
    linear.refresh_status = 400

    async with await _in_app_session(engine) as session:
        try:
            await integrations.refresh_connection(
                session,
                _make_client(linear),
                UUID(workspace),
                integrations.IntegrationProvider.LINEAR,
            )
        except Exception as exc:
            assert exc.code.value == "mcp.expired"  # type: ignore[attr-defined]
        else:
            raise AssertionError("a rejected refresh must raise")
        await session.commit()

    assert (await status_of(client, token))["status"] == "expired"
