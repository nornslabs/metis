"""Run recovery: pick up runs a dead or paused worker left in ``running``.

A live worker holds ``lock:run:{id}`` (a short TTL, kept alive by a heartbeat), so a
``running`` run without its lock lost its worker. Recovery enqueues ``run_graph`` for each;
the job continues from the run's last checkpoint. The run's first job id is still
remembered by Arq (it would drop a duplicate), so a recovery job gets its own id.

It runs at worker start and on a schedule (the ``recover_runs`` job), so a lost lock heals
without a restart. Three rules keep it safe to repeat:

- a run that moved within the grace window is left alone (a worker may be about to take
  its lock);
- a run is recovered at most ``RUN_RECOVERY_MAX_ATTEMPTS`` times, then fails with
  ``run.recovery_exhausted``;
- a run with no progress for ``RUN_STALL_SECONDS`` fails with ``run.stalled`` even when a
  lock is held, and its worker is asked to stop.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis.agent.run_events import RunEventPublisher
from metis.core.config import get_settings
from metis.core.db import get_session_maker, set_workspace
from metis.core.errors import ERROR_CATALOG, ErrorCode
from metis.core.jobs import enqueue
from metis.core.logging import get_logger
from metis.core.run_control import (
    RECOVERY_COUNT_TTL_SECONDS,
    lock_key,
    recovery_key,
    request_cancel,
)
from metis.modules import ideas
from metis.modules.ideas import RunRef, RunStatus

GRACE_MARGIN_SECONDS = 10

logger = get_logger(__name__)


async def recover_stuck_runs(
    redis: ArqRedis,
    sessions: async_sessionmaker[AsyncSession] | None = None,
    *,
    grace_seconds: float | None = None,
) -> int:
    """Re-enqueue every ``running`` run whose lock is gone; return how many.

    ``grace_seconds`` (default: the lock TTL plus a margin) is how recent a run's last update
    must be for a lock-less run to be left alone.
    """
    settings = get_settings()
    grace = (
        settings.run_lock_ttl_seconds + GRACE_MARGIN_SECONDS
        if grace_seconds is None
        else grace_seconds
    )
    maker = sessions or get_session_maker()
    async with maker() as session:
        refs = await ideas.list_running_runs(session)
    recovered = 0
    for ref in refs:
        try:
            recovered += await _handle(redis, maker, ref, grace)
        except Exception:  # noqa: BLE001  (one bad run must not stop the scan)
            logger.exception("run.recovery_item_failed", run_id=str(ref.run_id))
    return recovered


async def _handle(
    redis: ArqRedis, sessions: async_sessionmaker[AsyncSession], ref: RunRef, grace: float
) -> int:
    """Recover, fail or leave alone one ``running`` run; ``1`` when it was re-enqueued."""
    idle = (datetime.now(UTC) - ref.updated_at).total_seconds()
    if await redis.exists(lock_key(ref.run_id)):
        if idle >= get_settings().run_stall_seconds:
            await _stop_stalled(redis, sessions, ref)
        return 0
    if idle < grace:
        return 0
    done = int(await redis.get(recovery_key(ref.run_id)) or 0)
    if done >= get_settings().run_recovery_max_attempts:
        logger.error("run.recovery_exhausted", run_id=str(ref.run_id), attempts=done)
        await _fail(redis, sessions, ref, ErrorCode.RUN_RECOVERY_EXHAUSTED)
        return 0
    return await _enqueue(redis, ref, done + 1)


async def _enqueue(redis: ArqRedis, ref: RunRef, attempt: int) -> int:
    """Enqueue the run's recovery job; only a job that was really enqueued counts."""
    job = await enqueue(
        "run_graph",
        run_id=str(ref.run_id),
        workspace_id=str(ref.workspace_id),
        job_id=f"{ref.run_id}:recover:{int(time.time())}",
        pool=redis,
    )
    if job is None:
        return 0
    key = recovery_key(ref.run_id)
    await redis.incr(key)
    await redis.expire(key, RECOVERY_COUNT_TTL_SECONDS)
    logger.info("run.recovery_enqueued", run_id=str(ref.run_id), attempt=attempt)
    return 1


async def _stop_stalled(
    redis: ArqRedis, sessions: async_sessionmaker[AsyncSession], ref: RunRef
) -> None:
    """A live lock but no progress: fail the run and ask its worker to stop."""
    logger.error("run.stalled", run_id=str(ref.run_id))
    await _fail(redis, sessions, ref, ErrorCode.RUN_STALLED)
    await request_cancel(redis, ref.run_id)


async def _fail(
    redis: ArqRedis,
    sessions: async_sessionmaker[AsyncSession],
    ref: RunRef,
    code: ErrorCode,
) -> None:
    error = {"code": code.value, "message": ERROR_CATALOG[code].title}
    async with sessions() as session, session.begin():
        await set_workspace(session, ref.workspace_id)
        await ideas.mark_failed(session, ref.workspace_id, ref.run_id, error)
    await RunEventPublisher(str(ref.run_id), redis).status(RunStatus.FAILED.value, error=error)
