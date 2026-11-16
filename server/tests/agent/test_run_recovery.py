"""Crash recovery and the run lock: a run a dead worker left ``running`` continues from its
last checkpoint, and a live worker's run is never taken over.

A killed worker is simulated by cancelling the job while a node is hanging (what Arq's shutdown
does): the job ends without settling the run, so it stays ``running``, like after a kill.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from arq.connections import ArqRedis, RedisSettings, create_pool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.recovery import recover_stuck_runs
from metis.agent.run_lock import hold_run_lock
from metis.agent.specialists.stubs import stub_specialists
from metis.agent.state import MetisState
from metis.agent.supervisor import Specialist
from metis.core.jobs import AGENT_QUEUE
from metis.core.run_control import lock_key
from tests.agent.run_job_helpers import (
    QueuedRun,
    events_of,
    job_ctx,
    node_events,
    queued_run,
    run_job,
    run_row,
    statuses,
)
from tests.modules.conftest import REDIS_URL


class _KilledOnce:
    """The Researcher: the first call hangs until its job is cancelled (a killed worker),
    later calls work."""

    def __init__(self) -> None:
        self.calls = 0
        self.entered = asyncio.Event()
        self._stub = stub_specialists()[Specialist.RESEARCHER]

    async def __call__(self, state: MetisState) -> dict[str, Any]:
        self.calls += 1
        if self.calls == 1:
            self.entered.set()
            await asyncio.sleep(3600)
        return await self._stub(state)


@pytest.fixture
async def arq_pool(redis: Redis) -> ArqRedis:  # noqa: ARG001  (redis flushes the test database)
    pool = await create_pool(RedisSettings.from_dsn(REDIS_URL))
    yield pool
    await pool.aclose()


async def _killed_run(
    engine: AsyncEngine,
    redis: Redis,
    sessions: async_sessionmaker[AsyncSession],
    sub: str = "ada",
) -> tuple[QueuedRun, dict[str, Any], _KilledOnce]:
    researcher = _KilledOnce()
    ctx = job_ctx(redis, sessions, {Specialist.RESEARCHER: researcher})
    run = await queued_run(engine, sub)
    job = asyncio.create_task(run_job(ctx, run))
    await asyncio.wait_for(researcher.entered.wait(), timeout=10)
    job.cancel()  # what Arq's shutdown does to a running job
    with pytest.raises(asyncio.CancelledError):
        await job
    return run, ctx, researcher


async def test_a_killed_run_stays_running_and_frees_its_lock(
    engine: AsyncEngine,
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
) -> None:
    run, _, _ = await _killed_run(engine, redis, app_sessions)

    assert (await run_row(engine, run)).status == "running"
    assert not await redis.exists(lock_key(run.run_id))


async def test_recovery_re_enqueues_a_running_run_and_the_job_continues_from_the_checkpoint(
    engine: AsyncEngine,
    redis: Redis,
    arq_pool: ArqRedis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
) -> None:
    run, ctx, researcher = await _killed_run(engine, redis, app_sessions)
    seen = len(await events_of(redis, run))

    recovered = await recover_stuck_runs(arq_pool, app_sessions)

    [queued] = await arq_pool.queued_jobs(queue_name=AGENT_QUEUE)
    assert (recovered, queued.function) == (1, "run_graph")
    assert queued.kwargs == {"run_id": str(run.run_id), "workspace_id": str(run.workspace_id)}
    await run_job(ctx, run)  # what the worker does with that job
    after = (await events_of(redis, run))[seen:]
    assert (await run_row(engine, run)).status == "succeeded"
    assert statuses(after) == ["running", "succeeded"]
    # the interviewer steps finished before the kill are not run again
    assert node_events(after)[0] == ("node_started", "researcher")
    assert researcher.calls == 2


async def test_recovery_leaves_a_run_whose_lock_is_held_and_runs_not_running(
    engine: AsyncEngine,
    redis: Redis,
    arq_pool: ArqRedis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
) -> None:
    live, _, _ = await _killed_run(engine, redis, app_sessions, "ada")
    await redis.set(lock_key(live.run_id), "a-live-worker", ex=60)
    await queued_run(engine, "grace")  # queued, not running

    recovered = await recover_stuck_runs(arq_pool, app_sessions)

    assert recovered == 0
    assert await arq_pool.queued_jobs(queue_name=AGENT_QUEUE) == []


async def test_recovery_finds_running_runs_in_every_workspace(
    engine: AsyncEngine,
    redis: Redis,
    arq_pool: ArqRedis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
) -> None:
    await _killed_run(engine, redis, app_sessions, "ada")
    await _killed_run(engine, redis, app_sessions, "grace")

    assert await recover_stuck_runs(arq_pool, app_sessions) == 2


# ------------------------------------------------------------------------ lock
async def test_the_heartbeat_keeps_the_lock_alive_past_its_ttl(redis: Redis) -> None:
    run_id = uuid4()

    async with hold_run_lock(redis, run_id, ttl_seconds=1, heartbeat_seconds=0.3) as lock:
        await asyncio.sleep(1.6)
        assert (lock.acquired, lock.lost, await redis.exists(lock_key(run_id))) == (
            True,
            False,
            1,
        )

    assert not await redis.exists(lock_key(run_id))


async def test_a_lock_that_expires_without_a_heartbeat_frees_the_run(redis: Redis) -> None:
    run_id = uuid4()
    await redis.set(lock_key(run_id), "dead-worker", ex=1)

    await asyncio.sleep(1.2)

    async with hold_run_lock(redis, run_id, ttl_seconds=5, heartbeat_seconds=1) as lock:
        assert lock.acquired


async def test_a_lock_taken_over_is_reported_lost_and_not_released_by_the_old_owner(
    redis: Redis,
) -> None:
    run_id = uuid4()

    async with hold_run_lock(redis, run_id, ttl_seconds=3, heartbeat_seconds=0.2) as lock:
        await redis.set(lock_key(run_id), "new-owner", ex=30)
        await asyncio.sleep(0.5)
        assert lock.lost

    assert await redis.get(lock_key(run_id)) == b"new-owner"
