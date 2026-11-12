"""Arq job runtime: Redis settings, queue routing, idempotent enqueue, job logging.

Services enqueue work through :func:`enqueue`; the ``worker`` process runs it
(see ``metis.entrypoints.worker``) and the ``scheduler`` process only enqueues
periodic jobs (see ``metis.entrypoints.scheduler``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from arq.connections import ArqRedis, RedisSettings, create_pool
from arq.jobs import Job

from metis.core.config import get_settings
from metis.core.logging import bind_context, clear_context, get_logger

AGENT_QUEUE = "agent"
MAINTENANCE_QUEUE = "maintenance"

# Job name -> queue it runs on. A job must be registered here to be enqueued.
JOB_QUEUES: dict[str, str] = {
    "ping": AGENT_QUEUE,
    "outbox_relay": MAINTENANCE_QUEUE,
    "cleanup": MAINTENANCE_QUEUE,
}

# Job kwargs that, when present, are bound to every log line of the job.
LOG_CONTEXT_KWARGS = ("run_id", "workspace_id")

logger = get_logger(__name__)

JobFunction = Callable[..., Awaitable[Any]]


def redis_settings() -> RedisSettings:
    """Build Arq Redis settings from ``REDIS_URL``."""
    url = get_settings().redis_url
    return RedisSettings.from_dsn(url) if url else RedisSettings()


async def enqueue(
    job_name: str,
    *args: Any,
    job_id: str | None = None,
    pool: ArqRedis | None = None,
    **kwargs: Any,
) -> Job | None:
    """Enqueue ``job_name`` on its queue.

    ``job_id`` makes the enqueue idempotent: when a job with the same id already
    exists, nothing is enqueued and ``None`` is returned. Pass ``pool`` to reuse
    an open connection; otherwise one is opened and closed for this call.

    Raises:
        ValueError: ``job_name`` has no queue in :data:`JOB_QUEUES`.
    """
    queue = JOB_QUEUES.get(job_name)
    if queue is None:
        raise ValueError(f"Unknown job: {job_name!r}")

    if pool is not None:
        return await pool.enqueue_job(job_name, *args, _job_id=job_id, _queue_name=queue, **kwargs)

    async with await create_pool(redis_settings()) as owned:
        return await owned.enqueue_job(
            job_name, *args, _job_id=job_id, _queue_name=queue, **kwargs
        )


def logged_job(fn: JobFunction) -> JobFunction:
    """Bind ``job_id`` (and ``run_id``/``workspace_id`` when passed) to job logs.

    The context is cleared when the job ends so ids never leak into the next job.
    """

    @wraps(fn)
    async def wrapper(ctx: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        context = {"job_id": ctx.get("job_id")}
        context.update({k: kwargs[k] for k in LOG_CONTEXT_KWARGS if k in kwargs})
        bind_context(**context)
        logger.info("job.started", job=fn.__name__)
        try:
            return await fn(ctx, *args, **kwargs)
        finally:
            logger.info("job.finished", job=fn.__name__)
            clear_context(*context)

    return wrapper
