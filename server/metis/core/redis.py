"""The API's shared Redis client (cache data only; see ``architecture.md``).

One client per process, created on first use from ``REDIS_URL`` and closed in
the app lifespan. Routes get it through ``RedisDep``; tests override
``get_redis``. Short socket timeouts keep a Redis outage from stalling
requests: callers treat Redis errors as a cache miss.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis

from metis.core.config import get_settings

REDIS_TIMEOUT_SECONDS = 0.5

_client: Redis | None = None


def get_redis() -> Redis:
    """FastAPI dependency: the process-wide Redis client."""
    global _client
    if _client is None:
        _client = Redis.from_url(
            get_settings().redis_url,
            socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
            socket_timeout=REDIS_TIMEOUT_SECONDS,
        )
    return _client


async def close_redis() -> None:
    """Close the shared client, if one was opened."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


RedisDep = Annotated[Redis, Depends(get_redis)]

__all__ = ["REDIS_TIMEOUT_SECONDS", "RedisDep", "close_redis", "get_redis"]
