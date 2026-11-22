"""Arq worker entrypoints, one per queue.

Run with the arq CLI:

    arq metis.entrypoints.worker.AgentWorkerSettings
    arq metis.entrypoints.worker.MaintenanceWorkerSettings

Arq binds one queue and one ``max_jobs`` per process, so each queue has its own
settings class. ``maintenance`` runs one job at a time.
"""

from __future__ import annotations

from typing import Any

from metis.agent.checkpoint import setup_checkpointer
from metis.agent.recovery import recover_stuck_runs
from metis.core.config import get_settings
from metis.core.db import engine, get_session_maker
from metis.core.jobs import AGENT_QUEUE, MAINTENANCE_QUEUE, logged_job, redis_settings
from metis.core.logging import configure_logging, get_logger
from metis.core.outbox import relay_once
from metis.jobs.run_graph import run_graph

AGENT_MAX_JOBS = 10
JOB_TIMEOUT_MARGIN_SECONDS = 60
MAINTENANCE_MAX_JOBS = 1

logger = get_logger(__name__)


async def on_startup(ctx: dict[str, Any]) -> None:
    """Configure logging and open the DB engine; Arq provides ``ctx['redis']``."""
    configure_logging(get_settings())
    ctx["engine"] = engine()
    logger.info("worker.started")


async def agent_on_startup(ctx: dict[str, Any]) -> None:
    """``on_startup`` plus the graph's checkpoint tables (idempotent) and crash recovery."""
    await on_startup(ctx)
    await setup_checkpointer(get_settings().database_url)
    try:
        recovered = await recover_stuck_runs(ctx["redis"])
    except Exception:  # noqa: BLE001  (a failed scan must not keep the worker from starting)
        logger.exception("run.recovery_failed")
    else:
        logger.info("run.recovery_done", recovered=recovered)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    """Close the DB engine; Arq closes its own Redis pool."""
    await ctx["engine"].dispose()
    logger.info("worker.stopped")


@logged_job
async def ping(
    ctx: dict[str, Any], *, run_id: str | None = None, workspace_id: str | None = None
) -> str:
    """Test job proving the worker is alive."""
    return "pong"


@logged_job
async def outbox_relay(
    ctx: dict[str, Any], *, run_id: str | None = None, workspace_id: str | None = None
) -> None:
    """Deliver one batch of unpublished domain events from ``core.outbox``."""
    result = await relay_once(get_session_maker())
    logger.info(
        "outbox.relayed", published=result.published, failed=result.failed, dead=result.dead
    )


@logged_job
async def cleanup(
    ctx: dict[str, Any], *, run_id: str | None = None, workspace_id: str | None = None
) -> None:
    """No-op stub for nightly cleanup."""


class AgentWorkerSettings:
    """Worker for the ``agent`` queue."""

    functions = [ping, run_graph]
    queue_name = AGENT_QUEUE
    max_jobs = AGENT_MAX_JOBS
    # Arq's cap is a backstop past the runner's own timeout, which records the failure.
    job_timeout = get_settings().agent_job_timeout_seconds + JOB_TIMEOUT_MARGIN_SECONDS
    on_startup = agent_on_startup
    on_shutdown = on_shutdown
    redis_settings = redis_settings()


class MaintenanceWorkerSettings:
    """Worker for the ``maintenance`` queue; one job at a time."""

    functions = [outbox_relay, cleanup]
    queue_name = MAINTENANCE_QUEUE
    max_jobs = MAINTENANCE_MAX_JOBS
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = redis_settings()
