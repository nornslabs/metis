"""Arq worker entrypoint for background jobs.

The worker runs LangGraph agents and other background tasks.
Each job receives a run_id and uses it for structured logging context.

Note: The primary entry point is via the arq CLI command:
    arq metis.core.jobs.WorkerSettings

This module is for manual testing or custom worker instantiation.
"""

from __future__ import annotations

from typing import Any

from structlog.stdlib import BoundLogger

from metis.core.config import get_settings
from metis.core.logging import configure_logging, get_logger

# Configure logging
settings = get_settings()
configure_logging(settings)

logger: BoundLogger = get_logger(__name__)


# Job functions will be registered here as they are implemented
# For now, just a placeholder to keep the worker alive


async def ping(ctx: dict[str, Any]) -> str:
    """Health-check coroutine to prove the worker is alive."""
    logger.debug("health_check", message="pong")
    return "pong"


# Worker settings class for arq command
class WorkerSettings:
    """Arq worker settings for CLI usage."""

    functions = [ping]

    @property
    def redis_settings(self) -> Any:
        """Build Redis settings from the environment."""
        from arq.connections import RedisSettings  # noqa: PLC2704

        return RedisSettings.from_dsn(settings.redis_url)

    job_timeout = 300
    max_retries = 3


if __name__ == "__main__":
    import asyncio

    import arq

    logger.info("worker.starting", version=settings.app_version)

    async def run() -> None:
        worker = arq.Worker(functions=WorkerSettings.functions)
        await worker.async_run()

    asyncio.run(run())