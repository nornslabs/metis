"""Redis keys that coordinate one run between the API and the worker.

``lock:run:{run_id}`` is held by the worker running the run; ``cancel:{run_id}`` is set by
the API to ask the worker to stop at the next step boundary.
"""

from __future__ import annotations

from uuid import UUID

from redis.asyncio import Redis

LOCK_KEY_PREFIX = "lock:run:"
CANCEL_KEY_PREFIX = "cancel:"


def lock_key(run_id: UUID | str) -> str:
    """Redis key of the lock held while a worker runs ``run_id``."""
    return f"{LOCK_KEY_PREFIX}{run_id}"


def cancel_key(run_id: UUID | str) -> str:
    """Redis key whose presence asks the worker to cancel ``run_id``."""
    return f"{CANCEL_KEY_PREFIX}{run_id}"


async def cancel_requested(redis: Redis, run_id: UUID | str) -> bool:
    """Whether the API asked for ``run_id`` to be cancelled."""
    return bool(await redis.exists(cancel_key(run_id)))
