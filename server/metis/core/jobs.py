"""Arq worker settings.

This is a minimal registration of the worker. The real job registry (``run_graph``,
``market_scan``, outbox relay) is wired up as the agent graph and modules land.
Until then the worker starts, connects to Redis and idles instead of crashing.
"""

from __future__ import annotations

import os
from typing import Any

from arq.connections import RedisSettings


def _redis_settings() -> RedisSettings:
    """Build Redis settings from the environment at worker start time."""
    url = os.environ.get("REDIS_URL", "")
    if not url:
        return RedisSettings()
    return RedisSettings.from_dsn(url)


async def ping(ctx: dict[str, Any]) -> str:
    """Health-check coroutine used to prove the worker is alive."""
    return "pong"


class WorkerSettings:
    functions = [ping]
    redis_settings = _redis_settings()