"""The ``recover_runs`` job: re-enqueue runs that lost their worker (see ``agent/recovery.py``).

Enqueued by the scheduler on a short interval; it runs on the maintenance worker.
"""

from __future__ import annotations

from typing import Any

from metis.agent.recovery import recover_stuck_runs
from metis.core.jobs import logged_job
from metis.core.logging import get_logger

logger = get_logger(__name__)


@logged_job
async def recover_runs(ctx: dict[str, Any]) -> None:
    """Scan for ``running`` runs without a lock and recover, fail or leave each one."""
    recovered = await recover_stuck_runs(ctx["redis"])
    logger.info("run.recovery_done", recovered=recovered)
