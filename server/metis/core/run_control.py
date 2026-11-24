"""Redis keys that coordinate one run between the API and the worker.

``lock:run:{run_id}`` is held by the worker running the run; ``cancel:{run_id}`` is set by
the API to ask the worker to stop at the next step boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from redis.asyncio import Redis

if TYPE_CHECKING:
    from uuid import UUID

LOCK_KEY_PREFIX = "lock:run:"
CANCEL_KEY_PREFIX = "cancel:"
CANCEL_FLAG_TTL_SECONDS = 24 * 60 * 60


def lock_key(run_id: UUID | str) -> str:
    """Redis key of the lock held while a worker runs ``run_id``."""
    return f"{LOCK_KEY_PREFIX}{run_id}"


def cancel_key(run_id: UUID | str) -> str:
    """Redis key whose presence asks the worker to cancel ``run_id``."""
    return f"{CANCEL_KEY_PREFIX}{run_id}"


async def cancel_requested(redis: Redis, run_id: UUID | str) -> bool:
    """Whether the API asked for ``run_id`` to be cancelled."""
    return bool(await redis.exists(cancel_key(run_id)))


async def request_cancel(redis: Redis, run_id: UUID | str) -> None:
    """Ask the worker to stop ``run_id`` at its next step boundary."""
    await redis.set(cancel_key(run_id), "1", ex=CANCEL_FLAG_TTL_SECONDS)
