"""An idea's research: ``/v1/ideas/{idea_id}/research``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core import jobs
from metis.core.db import SessionDep
from metis.core.errors import ResearchNotFoundError, RunEnqueueError
from metis.core.logging import get_logger
from metis.modules.ideas import RunStarted, RunStatus, WorkflowRun
from metis.modules.identity import CurrentWorkspaceDep
from metis.modules.research import service
from metis.modules.research.dto import ResearchView

router = APIRouter(prefix="/ideas")
logger = get_logger(__name__)
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=255,
        pattern=r"^[!-~]+$",
        description="Printable ASCII, one per start; a retry sends the same key.",
    ),
]


@router.get("/{idea_id}/research", response_model=ResearchView)
async def get_latest_research(
    session: SessionDep, workspace: CurrentWorkspaceDep, idea_id: UUID
) -> ResearchView:
    """The idea's latest closed research snapshot; 404 ``research.not_found`` before one exists."""
    view = await service.snapshots.latest_snapshot(session, workspace.workspace.id, idea_id)
    if view is None:
        raise ResearchNotFoundError()
    return view


@router.post(
    "/{idea_id}/rescore", response_model=RunStarted, status_code=status.HTTP_202_ACCEPTED
)
async def rescore_latest_research(
    session: SessionDep,
    workspace: CurrentWorkspaceDep,
    idea_id: UUID,
    idempotency_key: IdempotencyKey,
) -> RunStarted:
    """Score the idea again using its latest completed market research."""
    return await _start_refresh(
        session,
        workspace.workspace.id,
        idea_id,
        idempotency_key,
        service.start_rescore,
    )


@router.post(
    "/{idea_id}/recheck-market",
    response_model=RunStarted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def recheck_market(
    session: SessionDep,
    workspace: CurrentWorkspaceDep,
    idea_id: UUID,
    idempotency_key: IdempotencyKey,
) -> RunStarted:
    """Collect a fresh market snapshot and score the idea again."""
    return await _start_refresh(
        session,
        workspace.workspace.id,
        idea_id,
        idempotency_key,
        service.start_market_recheck,
    )


async def _start_refresh(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    idempotency_key: str,
    start: Callable[[AsyncSession, UUID, UUID, str], Awaitable[WorkflowRun]],
) -> RunStarted:
    run = await start(session, workspace_id, idea_id, idempotency_key)
    await session.commit()
    if run.status == RunStatus.QUEUED:
        try:
            await jobs.enqueue(
                "run_graph",
                run_id=str(run.id),
                workspace_id=str(workspace_id),
                job_id=str(run.id),
            )
        except Exception as exc:
            logger.error("run.enqueue_failed", run_id=str(run.id), error=str(exc))
            raise RunEnqueueError("Could not queue the run; try again") from exc
    return RunStarted(run_id=run.id)
