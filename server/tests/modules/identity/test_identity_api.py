"""JWT auth, workspace scoping and the identity routes.

Seam: HTTP requests against the real FastAPI app (``ASGITransport``) with JWTs
signed here using the test ``AUTH_JWT_SECRET``/``AUTH_JWT_AUDIENCE``. The app's
request session runs on a migrated Postgres as the non-superuser ``metis_app``
role (``SET LOCAL ROLE``), so RLS is enforced exactly as in production.
Tests assert status codes, problem ``code`` values and response bodies only.

Set ``TEST_DATABASE_URL`` to a database migrated with ``alembic upgrade head``.
Tests skip only when Postgres is unreachable or not migrated.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import uuid4

import httpx
import jwt
import pytest
from api_helpers import (
    APP_ROLE,
    AUDIENCE,
    SECRET,
    add_member_directly,
    assert_problem,
    bearer,
    make_token,
    me,
)
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.core.config import get_settings
from metis.core.db import SessionDep
from metis.core.errors import PermissionDeniedError
from metis.entrypoints.api import app
from metis.modules import identity
from metis.modules.identity import CurrentUser, Membership, current_user, current_workspace

WEB_ORIGIN = get_settings().get_cors_origins()[0]

# ------------------------------------------------------------- test-only probe
# Routes that expose what the request session sees, to prove RLS scoping and
# rollback through HTTP. Mounted on the real app under a test-only prefix.
_probe = APIRouter(prefix="/v1/_test")


@_probe.get("/rls")
async def _rls_probe(
    session: SessionDep, _ws: Annotated[Membership, Depends(current_workspace)]
) -> dict[str, Any]:
    setting = await session.scalar(text("SELECT current_setting('app.workspace_id', true)"))
    rows = await session.execute(text("SELECT workspace_id, user_id FROM identity.members"))
    return {
        "workspace_setting": setting,
        "members": [{"workspace_id": str(w), "user_id": str(u)} for w, u in rows],
        "role": await session.scalar(text("SELECT current_user")),
    }


@_probe.post("/fail-after-write")
async def _fail_after_write(
    session: SessionDep, caller: Annotated[CurrentUser, Depends(current_user)]
) -> None:
    await identity.create_workspace(session, caller.user, "Doomed")
    raise PermissionDeniedError("boom")


app.include_router(_probe)


# ---------------------------------------------------------------- 401: tokens
async def test_missing_token_is_401_with_bearer_challenge(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/me")

    assert_problem(response, 401, "auth.unauthorized")
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "authorization",
    ["Basic dXNlcjpwYXNz", "Bearer", "Bearer not-a-jwt", "Token abc.def.ghi"],
)
async def test_malformed_authorization_is_401(
    client: httpx.AsyncClient, authorization: str
) -> None:
    response = await client.get("/v1/me", headers={"Authorization": authorization})

    assert_problem(response, 401, "auth.unauthorized")


async def test_token_signed_with_another_secret_is_401(client: httpx.AsyncClient) -> None:
    token = make_token(secret="another-secret-that-is-also-32-bytes-long")

    response = await client.get("/v1/me", headers=bearer(token))

    assert_problem(response, 401, "auth.unauthorized")


async def test_wrong_audience_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/me", headers=bearer(make_token(audience="someone-else")))

    assert_problem(response, 401, "auth.unauthorized")


async def test_token_expired_beyond_leeway_is_401_token_expired(
    client: httpx.AsyncClient,
) -> None:
    token = make_token(expires_in=timedelta(seconds=-60))

    response = await client.get("/v1/me", headers=bearer(token))

    assert_problem(response, 401, "auth.token_expired")
    assert response.headers["www-authenticate"] == "Bearer"


async def test_token_expired_within_leeway_is_accepted(client: httpx.AsyncClient) -> None:
    token = make_token(expires_in=timedelta(seconds=-10))

    response = await client.get("/v1/me", headers=bearer(token))

    assert response.status_code == 200, response.text


async def test_token_without_exp_is_401(client: httpx.AsyncClient) -> None:
    token = jwt.encode({"sub": "auth|ada", "email": "ada@example.com", "aud": AUDIENCE}, SECRET)

    response = await client.get("/v1/me", headers=bearer(token))

    assert_problem(response, 401, "auth.unauthorized")


async def test_unsigned_alg_none_token_is_401(client: httpx.AsyncClient) -> None:
    now = datetime.now(UTC)
    claims = {"sub": "auth|ada", "email": "ada@example.com", "aud": AUDIENCE}
    token = jwt.encode({**claims, "exp": now + timedelta(minutes=5)}, None, algorithm="none")

    response = await client.get("/v1/me", headers=bearer(token))

    assert_problem(response, 401, "auth.unauthorized")


@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")
async def test_token_with_other_hmac_algorithm_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/me", headers=bearer(make_token(algorithm="HS512")))

    assert_problem(response, 401, "auth.unauthorized")


async def test_token_with_rs256_header_is_401(client: httpx.AsyncClient) -> None:
    def segment(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    exp = int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())
    claims = {"sub": "auth|ada", "email": "ada@example.com", "aud": AUDIENCE, "exp": exp}
    token = f"{segment({'alg': 'RS256', 'typ': 'JWT'})}.{segment(claims)}.c2lnbmF0dXJl"

    response = await client.get("/v1/me", headers=bearer(token))

    assert_problem(response, 401, "auth.unauthorized")


@pytest.mark.parametrize("missing", ["sub", "email"])
async def test_token_missing_required_claim_is_401(client: httpx.AsyncClient, missing: str) -> None:
    token = make_token(sub=None) if missing == "sub" else make_token(email=None)

    response = await client.get("/v1/me", headers=bearer(token))

    assert_problem(response, 401, "auth.unauthorized")


async def test_token_with_invalid_email_claim_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/me", headers=bearer(make_token(email="not-an-email")))

    assert_problem(response, 401, "auth.unauthorized")


async def test_email_owned_by_another_account_is_409(client: httpx.AsyncClient) -> None:
    await me(client, make_token("auth|ada", "ada@example.com"))

    response = await client.get("/v1/me", headers=bearer(make_token("auth|eve", "ada@example.com")))

    assert_problem(response, 409, "common.conflict")


async def test_health_needs_no_token(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/health")

    assert response.status_code != 401


# ----------------------------------------------------------------------- /me
async def test_first_me_creates_user_and_personal_workspace(client: httpx.AsyncClient) -> None:
    body = await me(client, make_token(picture="https://example.com/ada.png"))

    assert body["user"]["email"] == "ada@example.com"
    assert body["user"]["name"] == "Ada"
    assert body["user"]["image"] == "https://example.com/ada.png"
    assert len(body["workspaces"]) == 1
    personal = body["workspaces"][0]
    assert personal["role"] == "owner"
    assert personal["workspace"]["is_personal"] is True
    assert body["current_workspace"] == personal


async def test_second_me_reuses_user_and_workspace_and_updates_name(
    client: httpx.AsyncClient,
) -> None:
    first = await me(client, make_token(name="Ada"))

    second = await me(client, make_token(name="Ada Lovelace"))

    assert second["user"]["id"] == first["user"]["id"]
    assert second["user"]["name"] == "Ada Lovelace"
    assert second["workspaces"] == first["workspaces"]


# ------------------------------------------------------------ workspace scope
async def test_member_workspace_header_selects_current_workspace(
    client: httpx.AsyncClient,
) -> None:
    token = make_token()
    created = await client.post("/v1/workspaces", json={"name": "Team"}, headers=bearer(token))
    team_id = created.json()["workspace"]["id"]

    body = await me(client, token, team_id)

    assert body["current_workspace"]["workspace"]["id"] == team_id
    assert body["current_workspace"]["role"] == "owner"


async def test_foreign_workspace_is_403(client: httpx.AsyncClient) -> None:
    bob = await me(client, make_token("auth|bob", "bob@example.com", "Bob"))
    bobs_workspace = bob["current_workspace"]["workspace"]["id"]

    response = await client.get("/v1/me", headers=bearer(make_token(), bobs_workspace))

    assert_problem(response, 403, "auth.forbidden")


async def test_unknown_workspace_is_403_like_a_foreign_one(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/me", headers=bearer(make_token(), uuid4()))

    assert_problem(response, 403, "auth.forbidden")


async def test_malformed_workspace_header_is_422(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/me", headers=bearer(make_token(), "not-a-uuid"))

    assert_problem(response, 422, "common.validation_failed")


async def rls_view(client: httpx.AsyncClient, token: str, workspace: str) -> Any:
    response = await client.get("/v1/_test/rls", headers=bearer(token, workspace))
    assert response.status_code == 200, response.text
    return response.json()


async def test_request_is_rls_scoped_to_the_chosen_workspace(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    # Ada owns Personal and Team; Bob is a member of Team only.
    ada_token, bob_token = make_token(), make_token("auth|bob", "bob@example.com", "Bob")
    ada = await me(client, ada_token)
    bob = await me(client, bob_token)
    ada_personal = ada["current_workspace"]["workspace"]["id"]
    team = await client.post("/v1/workspaces", json={"name": "Team"}, headers=bearer(ada_token))
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


async def test_failed_request_rolls_back_its_writes(client: httpx.AsyncClient) -> None:
    token = make_token()
    await me(client, token)

    response = await client.post("/v1/_test/fail-after-write", headers=bearer(token))

    assert_problem(response, 403, "auth.forbidden")
    names = [m["workspace"]["name"] for m in (await me(client, token))["workspaces"]]
    assert "Doomed" not in names


# ----------------------------------------------------------------- /workspaces
async def test_create_workspace_makes_caller_owner_and_lists_it(
    client: httpx.AsyncClient,
) -> None:
    token = make_token()

    created = await client.post("/v1/workspaces", json={"name": "  Team  "}, headers=bearer(token))
    listed = await client.get("/v1/workspaces", headers=bearer(token))

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
    client: httpx.AsyncClient, payload: dict[str, str]
) -> None:
    response = await client.post("/v1/workspaces", json=payload, headers=bearer(make_token()))

    assert_problem(response, 422, "common.validation_failed")


async def test_workspaces_routes_require_a_token(client: httpx.AsyncClient) -> None:
    listed = await client.get("/v1/workspaces")
    created = await client.post("/v1/workspaces", json={"name": "Team"})

    assert_problem(listed, 401, "auth.unauthorized")
    assert_problem(created, 401, "auth.unauthorized")


# ------------------------------------------------------------------------ CORS
async def test_cors_preflight_from_web_origin_is_allowed(client: httpx.AsyncClient) -> None:
    response = await client.options(
        "/v1/me",
        headers={
            "Origin": WEB_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,x-workspace-id",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WEB_ORIGIN
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed
    assert "x-workspace-id" in allowed


async def test_cors_preflight_from_other_origin_is_refused(client: httpx.AsyncClient) -> None:
    response = await client.options(
        "/v1/me",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )

    assert "access-control-allow-origin" not in response.headers
