"""Run business rules: create a run and move it along its status table.

Every function takes the caller's ``AsyncSession``, flushes but never commits (the
caller owns the transaction) and is scoped to the workspace id as well as RLS. Only
``list_running_runs`` reads across workspaces.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import IdeaNotFoundError, RunNotFoundError
from metis.core.logging import get_logger
from metis.helpers.time import utcnow
from metis.modules.ideas import repo
from metis.modules.ideas.dto import RunKind, RunRef, RunStatus, WorkflowRun
from metis.modules.ideas.helpers.run_transitions import TERMINAL_STATUSES, check_run_transition
from metis.modules.ideas.models import WorkflowRunRow

logger = get_logger(__name__)


async def create_run(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    *,
    idempotency_key: str | None = None,
) -> WorkflowRun:
    """Save a new ``queued`` run (unknown, archived or foreign idea: ``IdeaNotFoundError``)."""
    if await repo.ideas.get(session, workspace_id, idea_id) is None:
        raise IdeaNotFoundError()
    row = await repo.workflow_runs.create(
        session,
        workspace_id,
        idea_id,
        kind=RunKind.PIPELINE.value,
        idempotency_key=idempotency_key,
    )
    logger.info("run.created", run_id=str(row.id), idea_id=str(idea_id))
    return WorkflowRun.model_validate(row)


async def get_run(session: AsyncSession, workspace_id: UUID, run_id: UUID) -> WorkflowRun:
    """The run, or ``RunNotFoundError``."""
    return WorkflowRun.model_validate(await _get_row(session, workspace_id, run_id))


async def mark_running(session: AsyncSession, workspace_id: UUID, run_id: UUID) -> WorkflowRun:
    """``queued`` or ``awaiting_user`` → ``running``; a run already ``running`` (recovery)
    is returned unchanged. ``started_at`` is set the first time only."""
    row = await _get_row(session, workspace_id, run_id)
    if row.status == RunStatus.RUNNING:
        return WorkflowRun.model_validate(row)
    values: dict[str, Any] = {"pending_interrupt": None}
    if row.started_at is None:
        values["started_at"] = utcnow()
    return await _move(session, row, RunStatus.RUNNING, values)


async def mark_awaiting_user(
    session: AsyncSession, workspace_id: UUID, run_id: UUID, pending_interrupt: dict[str, Any]
) -> WorkflowRun:
    """``running`` → ``awaiting_user``, storing the question or approval the run waits on."""
    row = await _get_row(session, workspace_id, run_id)
    return await _move(
        session, row, RunStatus.AWAITING_USER, {"pending_interrupt": pending_interrupt}
    )


async def mark_succeeded(session: AsyncSession, workspace_id: UUID, run_id: UUID) -> WorkflowRun:
    """``running`` → ``succeeded``."""
    row = await _get_row(session, workspace_id, run_id)
    return await _move(session, row, RunStatus.SUCCEEDED, _finished())


async def mark_failed(
    session: AsyncSession, workspace_id: UUID, run_id: UUID, error: dict[str, Any]
) -> WorkflowRun:
    """``running`` → ``failed``, storing ``{code, message}``."""
    row = await _get_row(session, workspace_id, run_id)
    return await _move(session, row, RunStatus.FAILED, {**_finished(), "error": error})


async def mark_cancelled(session: AsyncSession, workspace_id: UUID, run_id: UUID) -> WorkflowRun:
    """``queued``, ``running`` or ``awaiting_user`` → ``cancelled``."""
    row = await _get_row(session, workspace_id, run_id)
    return await _move(session, row, RunStatus.CANCELLED, _finished())


async def list_running_runs(session: AsyncSession) -> list[RunRef]:
    """Every run in ``running`` in any workspace; the session needs no workspace set.

    Only crash recovery calls this. It returns ids, never run data."""
    pairs = await repo.workflow_runs.list_running(session)
    return [RunRef(run_id=run_id, workspace_id=workspace_id) for run_id, workspace_id in pairs]


def _finished() -> dict[str, Any]:
    return {"finished_at": utcnow(), "pending_interrupt": None}


async def _get_row(session: AsyncSession, workspace_id: UUID, run_id: UUID) -> WorkflowRunRow:
    row = await repo.workflow_runs.get(session, workspace_id, run_id)
    if row is None:
        raise RunNotFoundError()
    return row


async def _move(
    session: AsyncSession, row: WorkflowRunRow, target: RunStatus, values: dict[str, Any]
) -> WorkflowRun:
    current = RunStatus(row.status)
    check_run_transition(current, target)
    moved = await repo.workflow_runs.change_status(
        session,
        row.workspace_id,
        row.id,
        expected=current.value,
        values={**values, "status": target.value, "updated_at": utcnow()},
    )
    if moved is None:  # the run changed since it was read
        return await _reread_or_fail(session, row, target)
    logger.info("run.status_changed", run_id=str(row.id), status=target.value)
    return WorkflowRun.model_validate(moved)


async def _reread_or_fail(
    session: AsyncSession, row: WorkflowRunRow, target: RunStatus
) -> WorkflowRun:
    """A lost race: re-read; if the run already ended where we wanted, return it."""
    fresh = await _get_row(session, row.workspace_id, row.id)
    if fresh.status == target and target in TERMINAL_STATUSES:
        return WorkflowRun.model_validate(fresh)
    check_run_transition(RunStatus(fresh.status), target)
    raise RunNotFoundError()
