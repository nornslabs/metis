"""Postgres access for ``auth.identities`` (sign-in methods).

Queries only; not tenant data (no RLS).

Inserts run in a savepoint and return ``None`` on a unique conflict, so the caller's
transaction stays usable and a concurrent first sign-in can be retried.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.db import insert_or_none
from metis.helpers.ids import uuid7
from metis.modules.auth.models import IdentityRow
from metis.modules.auth.providers.base import AuthProviderName


async def get(
    session: AsyncSession, provider: AuthProviderName, subject: str
) -> IdentityRow | None:
    stmt = select(IdentityRow).where(
        IdentityRow.provider == provider, IdentityRow.subject == subject
    )
    return (await session.scalars(stmt)).one_or_none()


async def create(
    session: AsyncSession,
    *,
    user_id: UUID,
    provider: AuthProviderName,
    subject: str,
    email: str,
    email_verified: bool,
    now: datetime,
) -> IdentityRow | None:
    """Link ``(provider, subject)`` to ``user_id``; ``None`` if it is already linked."""
    stmt = (
        insert(IdentityRow)
        .values(
            id=uuid7(),
            user_id=user_id,
            provider=provider,
            subject=subject,
            email=email,
            email_verified=email_verified,
            created_at=now,
            last_login_at=now,
        )
        .returning(IdentityRow)
    )
    return await insert_or_none(session, stmt)


async def record_login(
    session: AsyncSession, identity_id: UUID, *, email: str, email_verified: bool, now: datetime
) -> None:
    """Set ``last_login_at`` and refresh what the provider says about the email."""
    await session.execute(
        update(IdentityRow)
        .where(IdentityRow.id == identity_id)
        .values(last_login_at=now, email=email, email_verified=email_verified)
    )
