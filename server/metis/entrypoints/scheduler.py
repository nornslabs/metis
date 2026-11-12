"""Scheduler process entrypoint.

The scheduler only enqueues jobs (market-watch ticks, nightly maintenance).
Until the real scheduler loop lands it blocks on an event so the process stays
up instead of crashing.
"""

from __future__ import annotations

import asyncio

import structlog

from metis.core.config import get_settings
from metis.core.logging import configure_logging

# Configure logging at startup
settings = get_settings()
configure_logging(settings)

logger = structlog.get_logger(__name__)


async def run() -> None:
    """Run the scheduler loop forever.

    The real implementation enqueues ``run_graph`` watch jobs and maintenance
    jobs on a cron schedule. Until then we block on an event so the process
    stays alive.
    """
    logger.info("scheduler.starting", version=settings.app_version)

    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        logger.info("scheduler.stopped")
    except Exception as e:
        logger.error("scheduler.failed", error=str(e))
        raise


def main() -> None:
    """Run the scheduler."""
    asyncio.run(run())


if __name__ == "__main__":
    main()