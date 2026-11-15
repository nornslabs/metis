"""Redis caches for the auth module: the session cache and OAuth login state.

Keys, TTLs and read/write/evict only; the rules that use them live in ``service``.

Session cache: entries (``auth:session:{hex hash}``) hold a ``SessionRecord``
for at most :data:`SESSION_CACHE_TTL_SECONDS`. Revoking writes a tombstone
(``auth:session:revoked:{hex hash}``) that outlives any entry
(:data:`SESSION_TOMBSTONE_TTL_SECONDS`) and deletes the entry. Readers check
the tombstone first, so a request that read the session from Postgres before
the revocation committed cannot bring it back by re-caching it. Redis errors
are logged and treated as a miss: auth falls back to Postgres.

OAuth login state: ``auth:oauth:{state}`` holds a ``PendingLogin`` for
:data:`OAUTH_STATE_TTL_SECONDS` and is taken back with ``GETDEL`` (single
use). Redis errors propagate: without the state a sign-in cannot finish, so
``service`` turns them into ``OAuthFailedError``. Values are never logged.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from metis.core.logging import get_logger
from metis.modules.auth.schemas import CacheLookup, PendingLogin, SessionRecord

logger = get_logger(__name__)


# --------------------------------------------------------------- session cache
SESSION_KEY_PREFIX = "auth:session:"
SESSION_TOMBSTONE_KEY_PREFIX = "auth:session:revoked:"
SESSION_CACHE_TTL_SECONDS = 60
# Longer than any entry a concurrent request could still write after reading
# the session before the revocation committed.
SESSION_TOMBSTONE_TTL_SECONDS = 2 * SESSION_CACHE_TTL_SECONDS


def session_key(token_hash: bytes) -> str:
    """Redis key of the session cache entry for ``token_hash``."""
    return f"{SESSION_KEY_PREFIX}{token_hash.hex()}"


def session_tombstone_key(token_hash: bytes) -> str:
    """Redis key marking the session ``token_hash`` as revoked."""
    return f"{SESSION_TOMBSTONE_KEY_PREFIX}{token_hash.hex()}"


def _session_cache_unavailable(op: str, exc: RedisError) -> None:
    logger.warning("auth.session_cache_unavailable", op=op, error=type(exc).__name__)


async def read_session(redis: Redis, token_hash: bytes) -> CacheLookup:
    """Look up ``token_hash``: revoked (tombstone), a cached record, or a miss."""
    try:
        raw, revoked = await redis.mget(session_key(token_hash), session_tombstone_key(token_hash))
    except RedisError as exc:
        _session_cache_unavailable("read", exc)
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


async def write_session(
    redis: Redis, token_hash: bytes, record: SessionRecord, now: datetime
) -> None:
    """Cache an active ``record`` for up to :data:`SESSION_CACHE_TTL_SECONDS`, never past expiry."""
    ttl = min(SESSION_CACHE_TTL_SECONDS, int((record.expires_at - now).total_seconds()))
    if ttl <= 0:
        return
    try:
        await redis.set(session_key(token_hash), record.model_dump_json(), ex=ttl)
    except RedisError as exc:
        _session_cache_unavailable("write", exc)


async def mark_sessions_revoked(redis: Redis, token_hashes: Sequence[bytes]) -> None:
    """Tombstone revoked sessions and drop their cache entries."""
    if not token_hashes:
        return
    try:
        async with redis.pipeline(transaction=True) as pipe:
            for token_hash in token_hashes:
                pipe.set(session_tombstone_key(token_hash), b"1", ex=SESSION_TOMBSTONE_TTL_SECONDS)
            pipe.delete(*(session_key(h) for h in token_hashes))
            await pipe.execute()
    except RedisError as exc:
        # Cached entries expire within SESSION_CACHE_TTL_SECONDS; until then they stay valid.
        logger.error("auth.session_cache_evict_failed", error=type(exc).__name__)


# ----------------------------------------------------------- oauth login state
OAUTH_KEY_PREFIX = "auth:oauth:"
OAUTH_STATE_TTL_SECONDS = 600


def oauth_key(state: str) -> str:
    """Redis key of the pending login started with ``state``."""
    return f"{OAUTH_KEY_PREFIX}{state}"


async def save_pending_login(redis: Redis, state: str, pending: PendingLogin) -> None:
    """Remember ``pending`` for :data:`OAUTH_STATE_TTL_SECONDS`; raises ``RedisError``."""
    await redis.set(oauth_key(state), pending.model_dump_json(), ex=OAUTH_STATE_TTL_SECONDS)


async def take_pending_login(redis: Redis, state: str) -> PendingLogin | None:
    """Take back (single use) the login ``state`` started; ``None`` if unknown or corrupt.

    Raises ``RedisError`` when Redis is unavailable.
    """
    stored = await redis.getdel(oauth_key(state))
    if stored is None:
        return None
    try:
        return PendingLogin.model_validate_json(stored)
    except ValidationError:
        logger.warning("auth.oauth_state_corrupt")
        return None
