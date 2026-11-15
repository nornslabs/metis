"""Session auth, workspace scoping and the identity routes.

Seam: HTTP requests against the real FastAPI app (``ASGITransport``) carrying a
session cookie from ``api_helpers.sign_in`` (a real session row). The app's
request session runs on a migrated Postgres as the non-superuser ``metis_app``
role (``SET LOCAL ROLE``), so RLS is enforced exactly as in production.
Tests assert status codes, problem ``code`` values and response bodies only.
Every route's 401 without a cookie is covered by ``test_route_auth.py``.

Set ``TEST_DATABASE_URL`` to a database migrated with ``alembic upgrade head``.
Tests skip only when Postgres or Redis is unreachable or not migrated.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
import pytest
from api_helpers import add_member_directly, me
from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.core.config import get_settings
from metis.core.db import SessionDep
from metis.core.errors import PermissionDeniedError
from metis.entrypoints.api import app
from metis.modules import identity
from metis.modules.auth import CurrentUserDep
from metis.modules.identity import CurrentWorkspaceDep
from tests.helpers.auth import (
    APP_ROLE,
    assert_problem,
    auth,
    sign_in,
)

WEB_ORIGIN = get_settings().get_cors_origins()[0]

# ------------------------------------------------------------- test-only probe
# Routes that expose what the request session sees, to prove RLS scoping and
# rollback through HTTP. Mounted on the real app under a test-only prefix.
_probe = APIRouter(prefix="/v1/_test")


@_probe.get("/rls")
async def _rls_probe(session: SessionDep, _ws: CurrentWorkspaceDep) -> dict[str, Any]:
    setting = await session.scalar(text("SELECT current_setting('app.workspace_id', true)"))
    rows = await session.execute(text("SELECT workspace_id, user_id FROM identity.members"))
    return {
        "workspace_setting": setting,
        "members": [{"workspace_id": str(w), "user_id": str(u)} for w, u in rows],
        "role": await session.scalar(text("SELECT current_user")),
    }


@_probe.post("/fail-after-write")
async def _fail_after_write(session: SessionDep, caller: CurrentUserDep) -> None:
    await identity.create_workspace(session, caller.user, "Doomed")
    raise PermissionDeniedError("boom")


app.include_router(_probe)


# ---------------------------------------------------------------------- public
async def test_health_needs_no_session(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/health")

    assert response.status_code != 401


# ----------------------------------------------------------------------- /me
async def test_first_me_creates_user_and_personal_workspace(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    body = await me(client, await sign_in(engine))

    assert body["user"]["email"] == "ada@example.com"
    assert body["user"]["name"] == "Ada"
    assert len(body["workspaces"]) == 1
    personal = body["workspaces"][0]
    assert personal["role"] == "owner"
    assert personal["workspace"]["is_personal"] is True
    assert body["current_workspace"] == personal


async def test_second_sign_in_reuses_user_and_workspace(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    first = await me(client, await sign_in(engine))

    second = await me(client, await sign_in(engine))

    assert second["user"]["id"] == first["user"]["id"]
    assert second["workspaces"] == first["workspaces"]


# ------------------------------------------------------------ workspace scope
async def test_member_workspace_header_selects_current_workspace(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
) -> None:
    token = await sign_in(engine)
    created = await client.post("/v1/workspaces", json={"name": "Team"}, headers=auth(token))
    team_id = created.json()["workspace"]["id"]

    body = await me(client, token, team_id)

    assert body["current_workspace"]["workspace"]["id"] == team_id
    assert body["current_workspace"]["role"] == "owner"


async def test_foreign_workspace_is_403(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    bob = await me(client, await sign_in(engine, "google-bob", "bob@example.com", "Bob"))
    bobs_workspace = bob["current_workspace"]["workspace"]["id"]

    response = await client.get("/v1/me", headers=auth(await sign_in(engine), bobs_workspace))

    assert_problem(response, 403, "auth.forbidden")


async def test_unknown_workspace_is_403_like_a_foreign_one(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    response = await client.get("/v1/me", headers=auth(await sign_in(engine), uuid4()))

    assert_problem(response, 403, "auth.forbidden")


async def test_malformed_workspace_header_is_422(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    response = await client.get("/v1/me", headers=auth(await sign_in(engine), "not-a-uuid"))

    assert_problem(response, 422, "common.validation_failed")


async def rls_view(client: httpx.AsyncClient, token: str, workspace: str) -> Any:
    response = await client.get("/v1/_test/rls", headers=auth(token, workspace))
    assert response.status_code == 200, response.text
    return response.json()


async def test_request_is_rls_scoped_to_the_chosen_workspace(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    # Ada owns Personal and Team; Bob is a member of Team only.
    ada_token = await sign_in(engine)
    bob_token = await sign_in(engine, "google-bob", "bob@example.com", "Bob")
    ada = await me(client, ada_token)
    bob = await me(client, bob_token)
    ada_personal = ada["current_workspace"]["workspace"]["id"]
    team = await client.post("/v1/workspaces", json={"name": "Team"}, headers=auth(ada_token))
    team_id = team.json()["workspace"]["id"]
    await add_member_directly(engine, team_id, bob["user"]["id"])
    bobs_team_row = {"workspace_id": team_id, "user_id": bob["user"]["id"]}

    in_personal = await rls_view(client, ada_token, ada_personal)
    in_team = await rls_view(client, ada_token, team_id)

    assert in_personal["role"] == APP_ROLE
    assert in_personal["workspace_setting"] == ada_personal
    assert bobs_team_row not in in_personal["members"]
    assert in_team["workspace_setting"] == team_id
    assert bobs_team_row in in_team["members"]


async def test_failed_request_rolls_back_its_writes(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    token = await sign_in(engine)
    await me(client, token)

    response = await client.post("/v1/_test/fail-after-write", headers=auth(token))

    assert_problem(response, 403, "auth.forbidden")
    names = [m["workspace"]["name"] for m in (await me(client, token))["workspaces"]]
    assert "Doomed" not in names


# ----------------------------------------------------------------- /workspaces
async def test_create_workspace_makes_caller_owner_and_lists_it(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
) -> None:
    token = await sign_in(engine)
    await me(client, token)  # the first /me creates the personal workspace

    created = await client.post("/v1/workspaces", json={"name": "  Team  "}, headers=auth(token))
    listed = await client.get("/v1/workspaces", headers=auth(token))

    assert created.status_code == 201, created.text
    assert created.json()["role"] == "owner"
    assert created.json()["workspace"]["name"] == "Team"
    assert created.json()["workspace"]["is_personal"] is False
    assert listed.status_code == 200
    body = listed.json()
    assert body["next_cursor"] is None
    assert [m["workspace"]["name"] for m in body["items"]] == ["Personal", "Team"]


@pytest.mark.parametrize("payload", [{"name": "   "}, {"name": "x" * 101}, {}])
async def test_create_workspace_with_invalid_name_is_422(
    client: httpx.AsyncClient,
    payload: dict[str, str],
    engine: AsyncEngine,
) -> None:
    response = await client.post(
        "/v1/workspaces", json=payload, headers=auth(await sign_in(engine))
    )

    assert_problem(response, 422, "common.validation_failed")


async def test_create_workspace_without_client_header_is_403_csrf_failed(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    headers = {"Cookie": auth(await sign_in(engine))["Cookie"]}

    response = await client.post("/v1/workspaces", json={"name": "Team"}, headers=headers)

    assert_problem(response, 403, "auth.csrf_failed")


# ------------------------------------------------------------------------ CORS
async def test_cors_preflight_from_web_origin_is_allowed(client: httpx.AsyncClient) -> None:
    response = await client.options(
        "/v1/me",
        headers={
            "Origin": WEB_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-metis-client,x-workspace-id",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WEB_ORIGIN
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "x-metis-client" in allowed
    assert "x-workspace-id" in allowed


async def test_cors_preflight_from_other_origin_is_refused(client: httpx.AsyncClient) -> None:
    response = await client.options(
        "/v1/me",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )

    assert "access-control-allow-origin" not in response.headers
