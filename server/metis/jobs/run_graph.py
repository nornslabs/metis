"""The ``run_graph`` job: run, resume or recover one agent run (see ``agent/runner.py``).

Enqueued as ``enqueue("run_graph", run_id=..., workspace_id=..., resume=...)``. The workspace
id is passed because RLS hides the run row until the session knows its workspace.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from metis.agent.runner import execute_run
from metis.core.jobs import logged_job


@logged_job
async def run_graph(
    ctx: dict[str, Any], *, run_id: str, workspace_id: str, resume: Any = None
) -> None:
    """Run ``run_id`` in ``workspace_id``; ``resume`` answers a run waiting for the user.

    ``ctx["run_deps"]`` (a ``RunnerDeps``) replaces the defaults; tests use it.
    """
    await execute_run(
        ctx["redis"], UUID(run_id), UUID(workspace_id), resume, deps=ctx.get("run_deps")
    )
