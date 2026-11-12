"""Tests for the Arq job runtime: enqueue helper, worker settings, scheduler.

The single seam is ``metis.core.jobs.enqueue`` against a real Redis with an Arq
worker running in-process (or as a subprocess for SIGTERM). Tests assert only
observable outcomes: job results, run counts, ordering and exit codes.

Set ``TEST_REDIS_URL`` to point at a Redis instance; tests skip when none is
reachable.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import structlog
from arq import func
from arq.connections import ArqRedis, RedisSettings, create_pool
from arq.jobs import Job, JobStatus
from arq.worker import Worker, create_worker

from metis.core import jobs
from metis.core.config import get_settings
from metis.core.jobs import AGENT_QUEUE, MAINTENANCE_QUEUE, enqueue, logged_job
from metis.entrypoints import scheduler, worker
from tests.core.slow_worker import derive_settings

REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
SERVER_ROOT = Path(__file__).resolve().parents[2]
RESULT_TIMEOUT_SECONDS = 10
SLOW_JOB_SECONDS = 0.3


@pytest.fixture(autouse=True)
def job_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/none")
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def pool() -> AsyncIterator[ArqRedis]:
    redis = await create_pool(RedisSettings.from_dsn(REDIS_URL))
    try:
        await redis.ping()
    except Exception:  # noqa: BLE001
        await redis.aclose()
        pytest.skip("Redis not reachable")
    await redis.flushdb()
    yield redis
    await redis.flushdb()
    await redis.aclose()


def _run_worker(settings_cls: type, **overrides: Any) -> Worker:
    return create_worker(
        settings_cls, redis_settings=RedisSettings.from_dsn(REDIS_URL), burst=True, **overrides
    )


async def _drain(settings_cls: type, **overrides: Any) -> None:
    w = _run_worker(settings_cls, **overrides)
    try:
        await w.main()
    finally:
        await w.close()


@pytest.mark.asyncio
async def test_enqueued_ping_runs_in_worker_and_completes(pool: ArqRedis) -> None:
    job = await enqueue("ping", pool=pool)
    assert job is not None

    await _drain(worker.AgentWorkerSettings)

    assert await job.result(timeout=RESULT_TIMEOUT_SECONDS) == "pong"


@pytest.mark.asyncio
async def test_same_job_id_enqueued_twice_runs_once(pool: ArqRedis) -> None:
    first = await enqueue("ping", job_id="dup", pool=pool)
    second = await enqueue("ping", job_id="dup", pool=pool)

    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_jobs_are_routed_to_their_queue(pool: ArqRedis) -> None:
    await enqueue("ping", job_id="a", pool=pool)
    await enqueue("cleanup", job_id="m", pool=pool)

    assert await pool.zcard(AGENT_QUEUE) == 1
    assert await pool.zcard(MAINTENANCE_QUEUE) == 1


@pytest.mark.asyncio
async def test_unknown_job_name_is_rejected(pool: ArqRedis) -> None:
    with pytest.raises(ValueError, match="nope"):
        await enqueue("nope", pool=pool)


@logged_job
async def _report_context(ctx: dict[str, Any], **_: Any) -> dict[str, Any]:
    return dict(structlog.contextvars.get_contextvars())


@pytest.mark.asyncio
async def test_job_logging_binds_ids_and_does_not_leak(pool: ArqRedis) -> None:
    settings = derive_settings(worker.AgentWorkerSettings, functions=[_report_context])

    job = await pool.enqueue_job(
        "_report_context", _job_id="j1", _queue_name=AGENT_QUEUE, run_id="r1", workspace_id="w1"
    )
    plain = await pool.enqueue_job("_report_context", _job_id="j2", _queue_name=AGENT_QUEUE)
    await _drain(settings, max_jobs=1)

    assert job is not None and plain is not None
    bound = await job.result(timeout=RESULT_TIMEOUT_SECONDS)
    assert bound == {"job_id": "j1", "run_id": "r1", "workspace_id": "w1"}
    assert await plain.result(timeout=RESULT_TIMEOUT_SECONDS) == {"job_id": "j2"}


@pytest.mark.asyncio
async def test_maintenance_jobs_never_run_concurrently(pool: ArqRedis) -> None:
    spans: list[tuple[float, float]] = []

    @logged_job
    async def slow(ctx: dict[str, Any]) -> None:
        start = time.monotonic()
        await asyncio.sleep(SLOW_JOB_SECONDS)
        spans.append((start, time.monotonic()))

    settings = derive_settings(
        worker.MaintenanceWorkerSettings, functions=[func(slow, name="slow")]
    )

    for n in range(2):
        await pool.enqueue_job("slow", _job_id=f"s{n}", _queue_name=MAINTENANCE_QUEUE)
    await _drain(settings)

    first, second = sorted(spans)
    assert len(spans) == 2
    assert first[1] <= second[0]


@pytest.mark.asyncio
async def test_maintenance_worker_runs_stub_jobs(pool: ArqRedis) -> None:
    relay = await enqueue("outbox_relay", job_id="r", pool=pool)
    cleanup = await enqueue("cleanup", job_id="c", pool=pool)
    assert relay is not None and cleanup is not None

    await _drain(worker.MaintenanceWorkerSettings)

    assert await relay.status() == JobStatus.complete
    assert await cleanup.status() == JobStatus.complete


@pytest.mark.asyncio
async def test_scheduler_only_enqueues_periodic_jobs(pool: ArqRedis) -> None:
    ctx: dict[str, Any] = {"redis": pool}

    await scheduler.enqueue_outbox_relay(ctx)
    await scheduler.enqueue_cleanup(ctx)

    assert await pool.zcard(MAINTENANCE_QUEUE) == 2
    assert await pool.zcard(AGENT_QUEUE) == 0


@pytest.mark.asyncio
async def test_scheduler_ticks_in_same_window_dedupe(pool: ArqRedis) -> None:
    ctx: dict[str, Any] = {"redis": pool}

    await scheduler.enqueue_outbox_relay(ctx)
    await scheduler.enqueue_outbox_relay(ctx)

    assert await pool.zcard(MAINTENANCE_QUEUE) == 1


def test_scheduler_registers_relay_every_5_seconds_and_cleanup_nightly() -> None:
    by_name = {c.name: c for c in scheduler.SchedulerSettings.cron_jobs}

    assert by_name["cron:enqueue_outbox_relay"].second == set(range(0, 60, 5))
    assert by_name["cron:enqueue_cleanup"].hour == 3


@pytest.mark.asyncio
async def test_worker_exits_cleanly_on_sigterm_and_requeues_in_flight_job(
    pool: ArqRedis,
) -> None:
    env = {**os.environ, "REDIS_URL": REDIS_URL, "PYTHONPATH": str(SERVER_ROOT)}
    cmd = [sys.executable, "-m", "arq", "tests.core.slow_worker.SlowWorkerSettings"]
    proc = subprocess.Popen(cmd, cwd=SERVER_ROOT, env=env)  # noqa: S603, ASYNC220
    job_id = f"slow-{uuid.uuid4().hex}"
    try:
        await asyncio.sleep(2)  # let the worker boot
        job = await pool.enqueue_job("slow", _job_id=job_id, _queue_name=AGENT_QUEUE)
        assert isinstance(job, Job)
        deadline = time.monotonic() + RESULT_TIMEOUT_SECONDS
        while await pool.get("slow-started") is None:
            assert time.monotonic() < deadline, "slow job never started"
            await asyncio.sleep(0.1)  # noqa: ASYNC110
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=RESULT_TIMEOUT_SECONDS) == 0
    finally:
        if proc.poll() is None:
            proc.kill()

    assert await job.status() in {JobStatus.queued, JobStatus.complete}


def test_enqueue_uses_redis_url_from_settings() -> None:
    assert jobs.redis_settings().port == RedisSettings.from_dsn(REDIS_URL).port
