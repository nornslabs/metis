"""Data access for ``identity.auth_identities`` (sign-in methods). Queries only.

Not tenant data: no RLS context needed. Inserts run in a savepoint and return
``None`` on a unique conflict so the caller's transaction stays usable and a
concurrent first sign-in can be retried.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.helpers.ids import uuid7
from metis.modules.identity.models import AuthIdentityRow
from metis.modules.identity.providers.base import AuthProviderName
from metis.modules.identity.repo import insert_or_none


async def get_identity(
    session: AsyncSession, provider: AuthProviderName, subject: str
) -> AuthIdentityRow | None:
    stmt = select(AuthIdentityRow).where(
        AuthIdentityRow.provider == provider, AuthIdentityRow.subject == subject
    )
    return (await session.scalars(stmt)).one_or_none()


async def insert_identity(
    session: AsyncSession,
    *,
    user_id: UUID,
    provider: AuthProviderName,
    subject: str,
    email: str,
    email_verified: bool,
    now: datetime,
) -> AuthIdentityRow | None:
    """Link ``(provider, subject)`` to ``user_id``; ``None`` if it is already linked."""
    stmt = (
        insert(AuthIdentityRow)
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
        .returning(AuthIdentityRow)
    )
    return await insert_or_none(session, stmt)


async def record_login(
    session: AsyncSession, identity_id: UUID, *, email: str, email_verified: bool, now: datetime
) -> None:
    """Set ``last_login_at`` and refresh what the provider says about the email."""
    await session.execute(
        update(AuthIdentityRow)
        .where(AuthIdentityRow.id == identity_id)
        .values(last_login_at=now, email=email, email_verified=email_verified)
    )
