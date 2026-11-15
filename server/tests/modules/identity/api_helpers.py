"""Helpers for the identity HTTP-seam tests (caller context, direct membership writes).

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
    """The caller's context as three routes report it: user, workspaces, current workspace.

    ``/v1/workspaces/current`` goes first: on a user's first call it creates the personal workspace.
    """
    current = await client.get("/v1/workspaces/current", headers=auth(token, workspace))
    assert current.status_code == 200, current.text
    user = await client.get("/v1/auth/me", headers=auth(token))
    assert user.status_code == 200, user.text
    listed = await client.get("/v1/workspaces", headers=auth(token))
    assert listed.status_code == 200, listed.text
    return {
        "user": user.json(),
        "workspaces": listed.json()["items"],
        "current_workspace": current.json(),
    }


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
