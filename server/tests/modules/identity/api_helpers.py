"""Helpers for the identity HTTP-seam tests (``/me``, direct membership writes).

Sign-in helpers live in ``tests/helpers/auth.py``; fixtures in
``tests/modules/conftest.py``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.helpers.auth import auth


async def me(client: httpx.AsyncClient, token: str, workspace: str | UUID | None = None) -> Any:
    response = await client.get("/v1/me", headers=auth(token, workspace))
    assert response.status_code == 200, response.text
    return response.json()


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
