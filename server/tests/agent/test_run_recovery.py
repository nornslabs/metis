"""Crash recovery and the run lock: a run a dead worker left ``running`` continues from its
last checkpoint, and a live worker's run is never taken over.

A killed worker is simulated by cancelling the job while a node is hanging (what Arq's shutdown
does): the job ends without settling the run, so it stays ``running``, like after a kill.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from arq.connections import ArqRedis, RedisSettings, create_pool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.recovery import recover_stuck_runs
from metis.agent.run_lock import hold_run_lock
from metis.agent.runner import Outcome, _settle
from metis.agent.specialists.stubs import stub_specialists
from metis.agent.state import MetisState
from metis.agent.supervisor import Specialist
from metis.core.db import set_workspace
from metis.core.jobs import AGENT_QUEUE
from metis.core.run_control import cancel_requested, lock_key, recovery_key
from metis.entrypoints.scheduler import enqueue_recover_runs
from metis.jobs.recover_runs import recover_runs
from metis.modules import ideas
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

    recovered = await recover_stuck_runs(arq_pool, app_sessions, grace_seconds=0)

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

    recovered = await recover_stuck_runs(arq_pool, app_sessions, grace_seconds=0)

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

    assert await recover_stuck_runs(arq_pool, app_sessions, grace_seconds=0) == 2


# --------------------------------------------------------------------- reaper
async def _age(engine: AsyncEngine, run: QueuedRun, seconds: int) -> None:
    """Make the run look like it last moved ``seconds`` ago."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ideas.workflow_runs SET updated_at = now() - make_interval(secs => :s) "
                "WHERE id = :id"
            ),
            {"s": seconds, "id": run.run_id},
        )


async def test_recovery_leaves_a_run_that_moved_within_the_grace_window(
    engine: AsyncEngine,
    redis: Redis,
    arq_pool: ArqRedis,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _killed_run(engine, redis, app_sessions)

    recovered = await recover_stuck_runs(arq_pool, app_sessions)  # default grace: lock TTL + 10 s

    assert recovered == 0
    assert await arq_pool.queued_jobs(queue_name=AGENT_QUEUE) == []


async def test_a_run_lost_for_longer_than_the_grace_window_is_recovered(
    engine: AsyncEngine,
    redis: Redis,
    arq_pool: ArqRedis,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run, _, _ = await _killed_run(engine, redis, app_sessions)
    await _age(engine, run, 120)

    assert await recover_stuck_runs(arq_pool, app_sessions) == 1


async def test_a_run_recovered_too_often_fails_with_run_recovery_exhausted(
    engine: AsyncEngine,
    redis: Redis,
    arq_pool: ArqRedis,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run, _, _ = await _killed_run(engine, redis, app_sessions)
    await redis.set(recovery_key(run.run_id), 3)  # three recoveries already (the limit)

    recovered = await recover_stuck_runs(arq_pool, app_sessions, grace_seconds=0)

    row = await run_row(engine, run)
    error = {"code": "run.recovery_exhausted", "message": "Run Interrupted Too Many Times"}
    assert (recovered, row.status, row.error) == (0, "failed", error)
    assert statuses(await events_of(redis, run))[-1] == "failed"
    assert await arq_pool.queued_jobs(queue_name=AGENT_QUEUE) == []


async def test_each_recovery_counts_towards_the_limit(
    engine: AsyncEngine,
    redis: Redis,
    arq_pool: ArqRedis,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run, _, _ = await _killed_run(engine, redis, app_sessions)

    await recover_stuck_runs(arq_pool, app_sessions, grace_seconds=0)

    assert int(await redis.get(recovery_key(run.run_id))) == 1
    assert await redis.ttl(recovery_key(run.run_id)) > 0


async def test_a_deduped_enqueue_does_not_count_as_a_recovery(
    engine: AsyncEngine,
    redis: Redis,
    arq_pool: ArqRedis,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run, _, _ = await _killed_run(engine, redis, app_sessions)

    await recover_stuck_runs(arq_pool, app_sessions, grace_seconds=0)
    await recover_stuck_runs(arq_pool, app_sessions, grace_seconds=0)  # same second: same job id

    assert int(await redis.get(recovery_key(run.run_id))) == 1


async def test_a_run_that_completes_steps_keeps_moving_its_updated_at(
    engine: AsyncEngine, redis: Redis, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, _, _ = await _killed_run(engine, redis, app_sessions)
    await _age(engine, run, 20 * 60)

    async with app_sessions() as session, session.begin():
        await set_workspace(session, run.workspace_id)
        await ideas.touch_run(session, run.workspace_id, run.run_id)

    async with engine.begin() as conn:
        idle = await conn.scalar(
            text(
                "SELECT extract(epoch FROM now() - updated_at) "
                "FROM ideas.workflow_runs WHERE id = :id"
            ),
            {"id": run.run_id},
        )
    assert idle < 60


async def test_a_run_with_a_live_lock_and_no_progress_fails_as_stalled_and_its_worker_is_stopped(
    engine: AsyncEngine,
    redis: Redis,
    arq_pool: ArqRedis,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run, _, _ = await _killed_run(engine, redis, app_sessions)
    await redis.set(lock_key(run.run_id), "a-hung-worker", ex=60)
    await _age(engine, run, 20 * 60)

    recovered = await recover_stuck_runs(arq_pool, app_sessions)

    row = await run_row(engine, run)
    assert (recovered, row.status) == (0, "failed")
    assert row.error == {"code": "run.stalled", "message": "Run Stalled"}
    assert await cancel_requested(redis, run.run_id)
    assert await arq_pool.queued_jobs(queue_name=AGENT_QUEUE) == []


async def test_a_run_with_a_live_lock_and_recent_progress_is_never_touched(
    engine: AsyncEngine,
    redis: Redis,
    arq_pool: ArqRedis,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run, _, _ = await _killed_run(engine, redis, app_sessions)
    await redis.set(lock_key(run.run_id), "a-live-worker", ex=60)
    await _age(engine, run, 5 * 60)  # idle, but under the stall limit

    await recover_stuck_runs(arq_pool, app_sessions, grace_seconds=0)

    assert (await run_row(engine, run)).status == "running"
    assert not await cancel_requested(redis, run.run_id)


async def test_a_second_worker_cannot_take_a_run_whose_lock_is_held(redis: Redis) -> None:
    run_id = uuid4()

    async with hold_run_lock(redis, run_id, ttl_seconds=30, heartbeat_seconds=10) as first:
        async with hold_run_lock(redis, run_id, ttl_seconds=30, heartbeat_seconds=10) as second:
            assert (first.acquired, second.acquired) == (True, False)


async def test_a_worker_that_lost_its_lock_writes_nothing_to_the_run() -> None:
    run = SimpleNamespace(id=uuid4(), workspace_id=uuid4())

    # deps and publisher are None: any write would fail on them
    await _settle(None, None, run, Outcome("lock_lost"))  # type: ignore[arg-type]


async def test_the_recover_runs_job_recovers_runs_that_lost_their_lock(
    engine: AsyncEngine,
    redis: Redis,
    arq_pool: ArqRedis,
    app_sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, _, _ = await _killed_run(engine, redis, app_sessions)
    await _age(engine, run, 120)
    monkeypatch.setattr("metis.agent.recovery.get_session_maker", lambda: app_sessions)

    await recover_runs({"redis": arq_pool})

    [queued] = await arq_pool.queued_jobs(queue_name=AGENT_QUEUE)
    assert queued.kwargs["run_id"] == str(run.run_id)


async def test_the_scheduler_enqueues_one_recover_runs_job_per_window(
    redis: Redis, arq_pool: ArqRedis
) -> None:
    await enqueue_recover_runs({"redis": arq_pool})
    await enqueue_recover_runs({"redis": arq_pool})

    jobs = await arq_pool.queued_jobs(queue_name="maintenance")
    assert [job.function for job in jobs] == ["recover_runs"]


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
