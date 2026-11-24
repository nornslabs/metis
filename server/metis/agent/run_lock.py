"""The per-run Redis lock: one worker runs a run at a time.

Taken with ``SET NX`` and an owner token, extended by a heartbeat while the run is live (one
node, such as an LLM call, can outlast any per-step refresh), and released only by its
owner. The TTL is short (``RUN_LOCK_TTL_SECONDS``) so a killed worker's lock frees soon and
crash recovery can pick the run up.
"""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError

from metis.core.logging import get_logger
from metis.core.run_control import lock_key

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = get_logger(__name__)

# Extend the TTL only while the key still holds our token / delete only our own key.
_EXTEND_SCRIPT = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end"
)
_RELEASE_SCRIPT = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)


@dataclass
class RunLock:
    """What the lock block yields. ``lost`` turns true if another worker took the key over."""

    acquired: bool
    lost: bool = False


@asynccontextmanager
async def hold_run_lock(
    redis: Redis, run_id: UUID, *, ttl_seconds: int, heartbeat_seconds: float
) -> AsyncGenerator[RunLock]:
    """Try to take ``run_id``'s lock; while the block runs, keep it alive."""
    key, token = lock_key(run_id), uuid4().hex
    if not await redis.set(key, token, nx=True, ex=ttl_seconds):
        yield RunLock(acquired=False)
        return
    lock = RunLock(acquired=True)
    heartbeat = asyncio.create_task(
        _heartbeat(redis, key, token, ttl_seconds, heartbeat_seconds, lock)
    )
    try:
        yield lock
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat
        await _release(redis, key, token)


async def _heartbeat(
    redis: Redis, key: str, token: str, ttl_seconds: int, interval: float, lock: RunLock
) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            extended = await redis.eval(_EXTEND_SCRIPT, 1, key, token, str(ttl_seconds))  # type: ignore[misc]
        except RedisError:
            logger.warning("run.lock_extend_failed", key=key)
            continue
        if not extended:
            lock.lost = True
            logger.error("run.lock_lost", key=key)
            return


async def _release(redis: Redis, key: str, token: str) -> None:
    try:
        await redis.eval(_RELEASE_SCRIPT, 1, key, token)  # type: ignore[misc]
    except RedisError:
        logger.warning("run.lock_release_failed", key=key)
