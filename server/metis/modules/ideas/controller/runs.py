"""Run routes: start, resume, cancel, read and list.

The API only records intent and queues the job; the worker runs the graph. Handlers commit
before they enqueue, so a worker never looks for a run that is not saved yet (the services
never commit, so the commit is here).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Query, status

from metis.core import events, jobs, run_control
from metis.core.db import SessionDep
from metis.core.errors import RunEnqueueError
from metis.core.logging import get_logger
from metis.core.redis import RedisDep
from metis.modules.ideas import service
from metis.modules.ideas.dto import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ResumeBody,
    RunCancelResult,
    RunPage,
    RunStarted,
    RunStatus,
    RunView,
)
from metis.modules.identity import CurrentWorkspaceDep

router = APIRouter()
logger = get_logger(__name__)

RUN_GRAPH_JOB = "run_graph"
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=255,
        pattern=r"^[!-~]+$",
        description="Printable ASCII, one per start; a retry sends the same one.",
    ),
]


@router.post(
    "/ideas/{idea_id}/runs", response_model=RunStarted, status_code=status.HTTP_202_ACCEPTED
)
async def start_run(
    session: SessionDep,
    workspace: CurrentWorkspaceDep,
    idea_id: UUID,
    idempotency_key: IdempotencyKey,
) -> RunStarted:
    """Start a run; the same ``Idempotency-Key`` returns the same run."""
    workspace_id = workspace.workspace.id
    run = await service.workflow_runs.start_run(session, workspace_id, idea_id, idempotency_key)
    await session.commit()
    if run.status == RunStatus.QUEUED:  # a retry re-enqueues; the same job id queues once
        await _enqueue(run.id, workspace_id, job_id=str(run.id))
    return RunStarted(run_id=run.id)


@router.post(
    "/runs/{run_id}/resume", response_model=RunStarted, status_code=status.HTTP_202_ACCEPTED
)
async def resume_run(
    session: SessionDep, workspace: CurrentWorkspaceDep, run_id: UUID, body: ResumeBody
) -> RunStarted:
    """Answer the question or approval the run waits on."""
    workspace_id = workspace.workspace.id
    run, value = await service.workflow_runs.prepare_resume(
        session, workspace_id, run_id, body.value
    )
    # One job id per pause (the version moves on every status change): a double submit queues once.
    await _enqueue(run.id, workspace_id, job_id=f"{run.id}:resume:{run.version}", resume=value)
    return RunStarted(run_id=run.id)


@router.post(
    "/runs/{run_id}/cancel", response_model=RunCancelResult, status_code=status.HTTP_202_ACCEPTED
)
async def cancel_run(
    session: SessionDep, workspace: CurrentWorkspaceDep, redis: RedisDep, run_id: UUID
) -> RunCancelResult:
    """Cancel now when the run is queued or waiting; a running run stops at its next step."""
    run = await service.workflow_runs.cancel_run(session, workspace.workspace.id, run_id)
    await session.commit()
    await run_control.request_cancel(redis, run.id)
    if run.status == RunStatus.CANCELLED:
        await events.publish(
            str(run.id), events.RunEventType.RUN_STATUS, {"status": "cancelled"}, redis=redis
        )
    return RunCancelResult(run_id=run.id, status=run.status)


@router.get("/runs/{run_id}", response_model=RunView)
async def get_run(session: SessionDep, workspace: CurrentWorkspaceDep, run_id: UUID) -> RunView:
    return await service.workflow_runs.get_run_view(session, workspace.workspace.id, run_id)


@router.get("/ideas/{idea_id}/runs", response_model=RunPage)
async def list_runs(
    session: SessionDep,
    workspace: CurrentWorkspaceDep,
    idea_id: UUID,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> RunPage:
    """The idea's runs, newest first; pass ``next_cursor`` as ``cursor`` for the next page."""
    return await service.workflow_runs.list_runs(
        session, workspace.workspace.id, idea_id, cursor, limit
    )


async def _enqueue(run_id: UUID, workspace_id: UUID, *, job_id: str, **kwargs: Any) -> None:
    """Queue ``run_graph``; the job takes its ids as strings."""
    try:
        await jobs.enqueue(
            RUN_GRAPH_JOB,
            run_id=str(run_id),
            workspace_id=str(workspace_id),
            job_id=job_id,
            **kwargs,
        )
    except Exception as exc:
        logger.error("run.enqueue_failed", run_id=str(run_id), error=str(exc))
        raise RunEnqueueError("Could not queue the run; try again") from exc
