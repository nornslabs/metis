"""Helpers shared by the identity HTTP-seam tests (sign-in, headers, problem checks).

Fixtures (``engine``, ``client``) live in this folder's ``conftest.py``.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from metis.core.config import get_settings
from metis.modules.identity import auth_service
from metis.modules.identity.auth_deps import CLIENT_HEADER, WEB_CLIENT, WORKSPACE_HEADER
from metis.modules.identity.providers.base import AuthProviderName, ProviderProfile

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/metis"
)
APP_ROLE = "metis_app"
SESSION_COOKIE = get_settings().session_cookie_name
# Workspaces cascade to members, provider keys and workspace settings.
TRUNCATE_IDENTITY = "TRUNCATE identity.members, identity.workspaces, identity.users CASCADE"


def google_profile(
    sub: str, email: str, name: str | None = None, image: str | None = None
) -> ProviderProfile:
    """A verified Google profile, as ``GoogleProvider.complete`` would return it."""
    return ProviderProfile(
        provider=AuthProviderName.GOOGLE,
        subject=sub,
        email=email,
        email_verified=True,
        name=name,
        avatar_url=image,
    )


async def create_user(
    engine: AsyncEngine,
    sub: str = "google-ada",
    email: str = "ada@example.com",
    name: str | None = "Ada",
) -> UUID:
    """Sign a Google user in (created on first use) without opening a session."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        signed_in = await auth_service.sign_in(session, google_profile(sub, email, name))
        await session.commit()
    return signed_in.user.id


async def sign_in(
    engine: AsyncEngine,
    sub: str = "google-ada",
    email: str = "ada@example.com",
    name: str | None = "Ada",
) -> str:
    """Sign a Google user in (created on first use) and return a new session token."""
    user_id = await create_user(engine, sub, email, name)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        created = await auth_service.create_session(session, user_id, "pytest/1.0", "127.0.0.1")
        await session.commit()
    return created.token


def auth(token: str, workspace_id: str | UUID | None = None) -> dict[str, str]:
    """Headers of a signed-in web request: session cookie, client header, workspace."""
    headers = {"Cookie": f"{SESSION_COOKIE}={token}", CLIENT_HEADER: WEB_CLIENT}
    if workspace_id is not None:
        headers[WORKSPACE_HEADER] = str(workspace_id)
    return headers


async def me(client: httpx.AsyncClient, token: str, workspace: str | UUID | None = None) -> Any:
    response = await client.get("/v1/me", headers=auth(token, workspace))
    assert response.status_code == 200, response.text
    return response.json()


def assert_problem(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == code


async def add_member_directly(engine: AsyncEngine, workspace_id: str, user_id: str) -> None:
    """Add the user as a plain ``member``, writing as the DB owner (no HTTP route yet)."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO identity.members (workspace_id, user_id, role) "
                "VALUES (:ws, :user, 'member')"
            ),
            {"ws": workspace_id, "user": user_id},
        )
