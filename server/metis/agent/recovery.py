"""Crash recovery: pick up runs a dead worker left in ``running``.

A live worker holds ``lock:run:{id}`` (a short TTL, kept alive by a heartbeat), so a
``running`` run without its lock lost its worker. Recovery enqueues ``run_graph`` for each;
the job continues from the run's last checkpoint. The run's first job id is still
remembered by Arq (it would drop a duplicate), so a recovery job gets its own id.
"""

from __future__ import annotations

import time

from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis.core.db import get_session_maker
from metis.core.jobs import enqueue
from metis.core.logging import get_logger
from metis.core.run_control import lock_key
from metis.modules import ideas

logger = get_logger(__name__)


async def recover_stuck_runs(
    redis: ArqRedis, sessions: async_sessionmaker[AsyncSession] | None = None
) -> int:
    """Re-enqueue every ``running`` run whose lock is gone; return how many."""
    async with (sessions or get_session_maker())() as session:
        refs = await ideas.list_running_runs(session)
    recovered = 0
    for ref in refs:
        if await redis.exists(lock_key(ref.run_id)):
            continue
        job_id = f"{ref.run_id}:recover:{int(time.time())}"
        job = await enqueue(
            "run_graph",
            run_id=str(ref.run_id),
            workspace_id=str(ref.workspace_id),
            job_id=job_id,
            pool=redis,
        )
        if job is not None:
            recovered += 1
            logger.info("run.recovery_enqueued", run_id=str(ref.run_id))
    return recovered
