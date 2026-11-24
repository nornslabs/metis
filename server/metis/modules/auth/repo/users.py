"""Postgres access for ``auth.users``. Queries only; not tenant data (no RLS)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.db import insert_or_none
from metis.helpers.ids import uuid7
from metis.modules.auth.dto import UserClaims
from metis.modules.auth.models import UserRow

if TYPE_CHECKING:
    from uuid import UUID


async def get(session: AsyncSession, user_id: UUID) -> UserRow | None:
    return await session.get(UserRow, user_id)


async def get_by_email(session: AsyncSession, email: str) -> UserRow | None:
    return (await session.scalars(select(UserRow).where(UserRow.email == email))).one_or_none()


async def create(session: AsyncSession, claims: UserClaims) -> UserRow | None:
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
