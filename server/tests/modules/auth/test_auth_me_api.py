"""``GET /v1/auth/me``: authenticates the session cookie and returns its user.

Seam: HTTP requests against the real app (request session as ``metis_app``), plus a read of
``identity.workspaces`` as the DB owner to show that auth alone creates no workspace.
"""

from __future__ import annotations

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.helpers.auth import assert_problem, auth, sign_in

ME = "/v1/auth/me"


async def test_me_returns_the_user_the_session_belongs_to(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    token = await sign_in(engine)

    response = await client.get(ME, headers=auth(token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == "ada@example.com"
    assert body["name"] == "Ada"
    assert set(body) == {"id", "email", "name", "image", "created_at"}


async def test_me_without_a_session_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get(ME)

    assert_problem(response, 401, "auth.not_signed_in")


async def test_me_with_an_unknown_session_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get(ME, headers=auth("not-a-real-session-token"))

    assert_problem(response, 401, "auth.session_expired")


async def test_me_does_not_create_a_personal_workspace(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    token = await sign_in(engine)

    await client.get(ME, headers=auth(token))

    async with engine.connect() as conn:
        count = await conn.scalar(text("SELECT count(*) FROM identity.workspaces"))
    assert count == 0
