"""Data access for sessions: Postgres rows plus a short-lived Redis cache.

Queries and cache operations only; expiry rules live in ``auth_service``.

Cache entries (``auth:session:{hex hash}``) hold a ``SessionRecord`` for at
most :data:`CACHE_TTL_SECONDS`. Revoking writes a tombstone
(``auth:session:revoked:{hex hash}``) that outlives any cache entry
(:data:`TOMBSTONE_TTL_SECONDS`) and deletes the entry. Readers check the
tombstone first, so a request that read the session from Postgres before the
revocation committed cannot bring it back by re-caching it. Redis errors are
logged and treated as a cache miss: auth falls back to Postgres.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.logging import get_logger
from metis.modules.identity.models import SessionRow
from metis.modules.identity.schemas import CacheLookup, SessionRecord

CACHE_KEY_PREFIX = "auth:session:"
TOMBSTONE_KEY_PREFIX = "auth:session:revoked:"
CACHE_TTL_SECONDS = 60
# Longer than any entry a concurrent request could still write after reading
# the session before the revocation committed.
TOMBSTONE_TTL_SECONDS = 2 * CACHE_TTL_SECONDS

logger = get_logger(__name__)


def cache_key(token_hash: bytes) -> str:
    """Redis key of the cache entry for ``token_hash``."""
    return f"{CACHE_KEY_PREFIX}{token_hash.hex()}"


def tombstone_key(token_hash: bytes) -> str:
    """Redis key marking ``token_hash`` as revoked."""
    return f"{TOMBSTONE_KEY_PREFIX}{token_hash.hex()}"


def _record(row: SessionRow) -> SessionRecord:
    return SessionRecord.model_validate(row)


# -------------------------------------------------------------------- Postgres
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
    return _record(row)


async def get_session_by_hash(session: AsyncSession, token_hash: bytes) -> SessionRecord | None:
    row = await session.scalar(select(SessionRow).where(SessionRow.token_hash == token_hash))
    return None if row is None else _record(row)


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


# ----------------------------------------------------------------------- cache
def _cache_unavailable(op: str, exc: RedisError) -> None:
    logger.warning("auth.session_cache_unavailable", op=op, error=type(exc).__name__)


async def read_cached(redis: Redis, token_hash: bytes) -> CacheLookup:
    """Look up ``token_hash``: revoked (tombstone), a cached record, or a miss."""
    try:
        raw, revoked = await redis.mget(cache_key(token_hash), tombstone_key(token_hash))
    except RedisError as exc:
        _cache_unavailable("read", exc)
        return CacheLookup()
    if revoked is not None:
        return CacheLookup(revoked=True)
    if raw is None:
        return CacheLookup()
    try:
        return CacheLookup(record=SessionRecord.model_validate_json(raw))
    except ValidationError:
        logger.warning("auth.session_cache_corrupt")
        return CacheLookup()


async def write_cached(
    redis: Redis, token_hash: bytes, record: SessionRecord, now: datetime
) -> None:
    """Cache an active ``record`` for up to :data:`CACHE_TTL_SECONDS`, never past expiry."""
    ttl = min(CACHE_TTL_SECONDS, int((record.expires_at - now).total_seconds()))
    if ttl <= 0:
        return
    try:
        await redis.set(cache_key(token_hash), record.model_dump_json(), ex=ttl)
    except RedisError as exc:
        _cache_unavailable("write", exc)


async def mark_revoked(redis: Redis, token_hashes: Sequence[bytes]) -> None:
    """Tombstone revoked sessions and drop their cache entries."""
    if not token_hashes:
        return
    try:
        async with redis.pipeline(transaction=True) as pipe:
            for token_hash in token_hashes:
                pipe.set(tombstone_key(token_hash), b"1", ex=TOMBSTONE_TTL_SECONDS)
            pipe.delete(*(cache_key(h) for h in token_hashes))
            await pipe.execute()
    except RedisError as exc:
        # Cached entries expire within CACHE_TTL_SECONDS; until then they stay valid.
        logger.error("auth.session_cache_evict_failed", error=type(exc).__name__)
