"""Reading users. ``get_user`` and ``find_user_by_email`` are public (re-exported by
``metis.modules.auth``); everything else is internal to auth.

Takes the caller's ``AsyncSession`` and never commits. Users are not tenant data: no RLS context.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.helpers.text import normalise_email
from metis.modules.auth import repo
from metis.modules.auth.dto import User


async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    """The user with ``user_id``, or ``None``."""
    row = await repo.users.get(session, user_id)
    return None if row is None else User.model_validate(row)


async def find_user_by_email(session: AsyncSession, email: str) -> User | None:
    """The user with ``email`` (trimmed, case-insensitive), or ``None``."""
    row = await repo.users.get_by_email(session, normalise_email(email))
    return None if row is None else User.model_validate(row)
