"""Session cache: a short-lived Redis copy of active sessions, plus revocation tombstones.

Entries (``auth:session:{hex hash}``) hold a ``SessionRecord`` for at most
:data:`TTL_SECONDS`. Revoking writes a tombstone (``auth:session:revoked:{hex hash}``)
that outlives any entry (:data:`TOMBSTONE_TTL_SECONDS`) and deletes the entry. Readers
check the tombstone first, so a request that read the session from Postgres before the
revocation committed cannot bring it back by re-caching it. Redis errors are logged and
treated as a miss: auth falls back to Postgres.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from metis.core.logging import get_logger
from metis.modules.auth.dto import CacheLookup, SessionRecord

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

KEY_PREFIX = "auth:session:"
TOMBSTONE_KEY_PREFIX = "auth:session:revoked:"
TTL_SECONDS = 60
# Longer than any entry a concurrent request could still write after reading
# the session before the revocation committed.
TOMBSTONE_TTL_SECONDS = 2 * TTL_SECONDS


def key(token_hash: bytes) -> str:
    """Redis key of the session cache entry for ``token_hash``."""
    return f"{KEY_PREFIX}{token_hash.hex()}"


def tombstone_key(token_hash: bytes) -> str:
    """Redis key marking the session ``token_hash`` as revoked."""
    return f"{TOMBSTONE_KEY_PREFIX}{token_hash.hex()}"


async def read(redis: Redis, token_hash: bytes) -> CacheLookup:
    """Look up ``token_hash``: revoked (tombstone), a cached record, or a miss."""
    try:
        raw, revoked = await redis.mget(key(token_hash), tombstone_key(token_hash))
    except RedisError as exc:
        _unavailable("read", exc)
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


async def write(redis: Redis, token_hash: bytes, record: SessionRecord, now: datetime) -> None:
    """Cache an active ``record`` for up to :data:`TTL_SECONDS`, never past expiry."""
    ttl = min(TTL_SECONDS, int((record.expires_at - now).total_seconds()))
    if ttl <= 0:
        return
    try:
        await redis.set(key(token_hash), record.model_dump_json(), ex=ttl)
    except RedisError as exc:
        _unavailable("write", exc)


async def mark_revoked(redis: Redis, token_hashes: Sequence[bytes]) -> None:
    """Tombstone revoked sessions and drop their cache entries."""
    if not token_hashes:
        return
    try:
        async with redis.pipeline(transaction=True) as pipe:
            for token_hash in token_hashes:
                pipe.set(tombstone_key(token_hash), b"1", ex=TOMBSTONE_TTL_SECONDS)
            pipe.delete(*(key(h) for h in token_hashes))
            await pipe.execute()
    except RedisError as exc:
        # Cached entries expire within TTL_SECONDS; until then they stay valid.
        logger.error("auth.session_cache_evict_failed", error=type(exc).__name__)


logger = get_logger(__name__)


def _unavailable(op: str, exc: RedisError) -> None:
    logger.warning("auth.session_cache_unavailable", op=op, error=type(exc).__name__)
