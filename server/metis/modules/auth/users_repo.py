"""Data access for ``auth.users``. Queries only; no business rules.

Not tenant data: no RLS context needed.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.db import insert_or_none
from metis.helpers.ids import uuid7
from metis.modules.auth.models import UserRow
from metis.modules.auth.schemas import UserClaims


async def get_user(session: AsyncSession, user_id: UUID) -> UserRow | None:
    return await session.get(UserRow, user_id)


async def get_user_by_email(session: AsyncSession, email: str) -> UserRow | None:
    return (await session.scalars(select(UserRow).where(UserRow.email == email))).one_or_none()


async def insert_user(session: AsyncSession, claims: UserClaims) -> UserRow | None:
    """Insert a new user; ``None`` if its email is already taken."""
    stmt = (
        insert(UserRow)
        .values(
            id=uuid7(),
            email=claims.email,
            name=claims.name,
            image=claims.image,
        )
        .returning(UserRow)
    )
    return await insert_or_none(session, stmt)
