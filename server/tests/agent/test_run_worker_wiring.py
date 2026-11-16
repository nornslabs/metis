"""The worker runs ``run_graph`` on the agent queue, and its settings keep the lock alive."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from metis.core.config import Settings
from metis.core.jobs import AGENT_QUEUE, JOB_QUEUES
from metis.entrypoints.worker import AgentWorkerSettings, MaintenanceWorkerSettings
from metis.jobs.run_graph import run_graph


def test_run_graph_is_an_agent_queue_job_only_the_agent_worker_runs() -> None:
    assert JOB_QUEUES["run_graph"] == AGENT_QUEUE
    assert run_graph in AgentWorkerSettings.functions
    assert run_graph not in MaintenanceWorkerSettings.functions


def test_the_lock_defaults_expire_within_a_minute_with_a_heartbeat_well_inside() -> None:
    settings = Settings()

    assert settings.run_lock_ttl_seconds == 60
    assert settings.run_lock_heartbeat_seconds == 20


def test_a_heartbeat_that_cannot_keep_the_lock_alive_is_refused() -> None:
    with pytest.raises(ValidationError, match="heartbeat"):
        Settings(run_lock_ttl_seconds=10, run_lock_heartbeat_seconds=6)
