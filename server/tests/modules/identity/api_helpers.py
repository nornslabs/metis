"""Helpers shared by the identity HTTP-seam tests (tokens, headers, problem checks).

Fixtures (``engine``, ``client``) live in this folder's ``conftest.py``.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.core.config import get_settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/metis"
)
APP_ROLE = "metis_app"
SECRET = get_settings().auth_jwt_secret
AUDIENCE = get_settings().auth_jwt_audience
# Workspaces cascade to members, provider keys and workspace settings.
TRUNCATE_IDENTITY = "TRUNCATE identity.members, identity.workspaces, identity.users CASCADE"


def make_token(
    sub: str | None = "auth|ada",
    email: str | None = "ada@example.com",
    name: str | None = "Ada",
    *,
    audience: str = AUDIENCE,
    secret: str = SECRET,
    algorithm: str = "HS256",
    expires_in: timedelta = timedelta(minutes=5),
    picture: str | None = None,
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {"aud": audience, "iat": now, "exp": now + expires_in}
    for key, value in {"sub": sub, "email": email, "name": name, "picture": picture}.items():
        if value is not None:
            claims[key] = value
    return jwt.encode(claims, secret, algorithm=algorithm)


def bearer(token: str, workspace_id: str | UUID | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if workspace_id is not None:
        headers["X-Workspace-Id"] = str(workspace_id)
    return headers


async def me(client: httpx.AsyncClient, token: str, workspace: str | UUID | None = None) -> Any:
    response = await client.get("/v1/me", headers=bearer(token, workspace))
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
