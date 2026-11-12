"""Test-only worker settings with a slow job, used by the SIGTERM test."""

from __future__ import annotations

import asyncio
from typing import Any

from metis.core.jobs import logged_job
from metis.entrypoints.worker import AgentWorkerSettings

SLOW_JOB_SECONDS = 30


@logged_job
async def slow(ctx: dict[str, Any]) -> None:
    """Signal that the job started, then run long enough to be interrupted."""
    await ctx["redis"].set("slow-started", "1", ex=60)
    await asyncio.sleep(SLOW_JOB_SECONDS)


def derive_settings(base: type, **overrides: Any) -> type:
    """Copy ``base`` settings with overrides.

    Arq reads only a settings class's own ``__dict__``, so plain subclassing would
    drop inherited queue name, concurrency and Redis settings.
    """
    inherited = {
        name: value
        for klass in reversed(base.__mro__)
        for name, value in vars(klass).items()
        if not name.startswith("__")
    }
    return type("DerivedSettings", (), {**inherited, **overrides})


SlowWorkerSettings = derive_settings(AgentWorkerSettings, functions=[slow])
