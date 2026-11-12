"""Scheduler process: Arq cron jobs that only enqueue work.

Run with ``python -m metis.entrypoints.scheduler`` (or the arq CLI on
``SchedulerSettings``). Real work happens in the worker processes.
"""

from __future__ import annotations

import time
from typing import Any

from arq import cron
from arq.worker import run_worker

from metis.core.config import get_settings
from metis.core.jobs import enqueue, redis_settings
from metis.core.logging import configure_logging, get_logger

OUTBOX_RELAY_INTERVAL_SECONDS = 5
CLEANUP_HOUR_UTC = 3
SCHEDULER_QUEUE = "scheduler"
SECONDS_PER_DAY = 86_400

logger = get_logger(__name__)


async def enqueue_outbox_relay(ctx: dict[str, Any]) -> None:
    """Enqueue one ``outbox_relay`` per 5-second window; duplicate ticks dedupe."""
    window = int(time.time()) // OUTBOX_RELAY_INTERVAL_SECONDS
    await enqueue("outbox_relay", job_id=f"outbox_relay:{window}", pool=ctx["redis"])


async def enqueue_cleanup(ctx: dict[str, Any]) -> None:
    """Enqueue one ``cleanup`` per day; duplicate ticks dedupe."""
    day = int(time.time()) // SECONDS_PER_DAY
    await enqueue("cleanup", job_id=f"cleanup:{day}", pool=ctx["redis"])


async def on_startup(ctx: dict[str, Any]) -> None:
    configure_logging(get_settings())
    logger.info("scheduler.started")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    logger.info("scheduler.stopped")


class SchedulerSettings:
    """Arq settings: cron jobs only, no registered functions."""

    functions: list[Any] = []
    cron_jobs = [
        cron(enqueue_outbox_relay, second=set(range(0, 60, OUTBOX_RELAY_INTERVAL_SECONDS))),
        cron(enqueue_cleanup, hour=CLEANUP_HOUR_UTC, minute=0, second=0),
    ]
    queue_name = SCHEDULER_QUEUE
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = redis_settings()


def main() -> None:
    """Run the scheduler until SIGTERM/SIGINT."""
    run_worker(SchedulerSettings)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
