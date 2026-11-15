"""Postgres access for the auth module: users, sign-in identities and sessions.

Queries only; business rules (expiry, sign-in matching) live in ``service``.
Not tenant data: no RLS context needed. Inserts that can hit a unique
constraint run in a savepoint (``insert_or_none``) and return ``None`` on a
conflict, so the caller's transaction stays usable and a concurrent first
sign-in can be retried.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.db import insert_or_none
from metis.helpers.ids import uuid7
from metis.modules.auth.models import AuthIdentityRow, SessionRow, UserRow
from metis.modules.auth.providers.base import AuthProviderName
from metis.modules.auth.schemas import SessionRecord, UserClaims


# ----------------------------------------------------------------------- users
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


# ------------------------------------------------------------- auth identities
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


# -------------------------------------------------------------------- sessions
def _session_record(row: SessionRow) -> SessionRecord:
    return SessionRecord.model_validate(row)


async def insert_session(
    session: AsyncSession,
    *,
    user_id: UUID,
    token_hash: bytes,
    now: datetime,
    expires_at: datetime,
    user_agent: str | None,
    ip: str | None,
) -> SessionRecord:
    row = SessionRow(
        user_id=user_id,
        token_hash=token_hash,
        created_at=now,
        last_seen_at=now,
        expires_at=expires_at,
        user_agent=user_agent,
        ip=ip,
    )
    session.add(row)
    await session.flush()
    return _session_record(row)


async def get_session_by_hash(session: AsyncSession, token_hash: bytes) -> SessionRecord | None:
    row = await session.scalar(select(SessionRow).where(SessionRow.token_hash == token_hash))
    return None if row is None else _session_record(row)


async def touch_session(session: AsyncSession, session_id: UUID, now: datetime) -> None:
    await session.execute(
        update(SessionRow).where(SessionRow.id == session_id).values(last_seen_at=now)
    )


async def revoke_session(session: AsyncSession, token_hash: bytes, now: datetime) -> UUID | None:
    """Revoke the active session with ``token_hash``; return its id, or ``None`` if none."""
    stmt = (
        update(SessionRow)
        .where(SessionRow.token_hash == token_hash, SessionRow.revoked_at.is_(None))
        .values(revoked_at=now)
        .returning(SessionRow.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def revoke_user_sessions(session: AsyncSession, user_id: UUID, now: datetime) -> list[bytes]:
    """Revoke every active session of ``user_id``; return their token hashes."""
    stmt = (
        update(SessionRow)
        .where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
        .values(revoked_at=now)
        .returning(SessionRow.token_hash)
    )
    return list((await session.execute(stmt)).scalars())
