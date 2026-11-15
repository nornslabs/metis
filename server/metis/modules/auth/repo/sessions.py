"""Postgres access for ``auth.sessions``. Queries only; expiry rules live in ``service``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from metis.modules.auth.dto import SessionRecord
from metis.modules.auth.models import SessionRow


async def create(
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
    return _record(row)


async def get_by_hash(session: AsyncSession, token_hash: bytes) -> SessionRecord | None:
    row = await session.scalar(select(SessionRow).where(SessionRow.token_hash == token_hash))
    return None if row is None else _record(row)


async def touch(session: AsyncSession, session_id: UUID, now: datetime) -> None:
    await session.execute(
        update(SessionRow).where(SessionRow.id == session_id).values(last_seen_at=now)
    )


async def revoke(session: AsyncSession, token_hash: bytes, now: datetime) -> UUID | None:
    """Revoke the active session with ``token_hash``; return its id, or ``None`` if none."""
    stmt = (
        update(SessionRow)
        .where(SessionRow.token_hash == token_hash, SessionRow.revoked_at.is_(None))
        .values(revoked_at=now)
        .returning(SessionRow.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def revoke_all_for_user(session: AsyncSession, user_id: UUID, now: datetime) -> list[bytes]:
    """Revoke every active session of ``user_id``; return their token hashes."""
    stmt = (
        update(SessionRow)
        .where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
        .values(revoked_at=now)
        .returning(SessionRow.token_hash)
    )
    return list((await session.execute(stmt)).scalars())


def _record(row: SessionRow) -> SessionRecord:
    return SessionRecord.model_validate(row)
