"""Sign-in helpers shared by the auth and identity HTTP-seam tests.

Fixtures (``engine``, ``redis``, ``client``, ``http``) live in
``tests/modules/conftest.py``.
"""

from __future__ import annotations

import os
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from metis.core.config import get_settings
from metis.modules.auth import service as auth_service
from metis.modules.auth.deps import CLIENT_HEADER, WEB_CLIENT
from metis.modules.auth.providers.base import AuthProviderName, ProviderProfile
from metis.modules.identity.deps import WORKSPACE_HEADER

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/metis"
)
APP_ROLE = "metis_app"
SESSION_COOKIE = get_settings().session_cookie_name
# Users cascade to sessions, sign-in identities and members; workspaces to
# members, provider keys and workspace settings.
TRUNCATE_USERS = "TRUNCATE identity.members, identity.workspaces, auth.users CASCADE"


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


def assert_problem(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == code
