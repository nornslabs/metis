"""Run business rules: create a run and move it along its status table.

Every function takes the caller's ``AsyncSession``, flushes but never commits (the
caller owns the transaction) and is scoped to the workspace id as well as RLS. Only
``list_running_runs`` reads across workspaces.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import (
    IdeaNotFoundError,
    IdempotencyMismatchError,
    IllegalRunTransition,
    LlmNotReadyError,
    RunAlreadyRunningError,
    RunNotFoundError,
)
from metis.core.logging import get_logger
from metis.helpers.time import utcnow
from metis.modules import identity
from metis.modules.ideas import repo
from metis.modules.ideas.dto import (
    DEFAULT_PAGE_SIZE,
    RunKind,
    RunPage,
    RunRef,
    RunStatus,
    RunView,
    WorkflowRun,
)
from metis.modules.ideas.helpers.cursor import decode_cursor, encode_cursor
from metis.modules.ideas.helpers.resume_value import check_resume_value
from metis.modules.ideas.helpers.run_transitions import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    check_run_transition,
)
from metis.modules.ideas.models import WorkflowRunRow

logger = get_logger(__name__)

_LLM_NOT_READY_TEXT = {
    identity.KeyReadiness.NOT_CONFIGURED: "Add your LLM key in Settings, then test it.",
    identity.KeyReadiness.NOT_TESTED: "Test your LLM key in Settings before starting a run.",
    identity.KeyReadiness.TEST_FAILED: "Your LLM key failed its test. Fix it in Settings.",
}


async def create_run(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    *,
    idempotency_key: str | None = None,
    user_prompt: str | None = None,
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
        user_prompt=user_prompt,
    )
    logger.info("run.created", run_id=str(row.id), idea_id=str(idea_id))
    return WorkflowRun.model_validate(row)


async def start_run(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    idempotency_key: str,
    user_prompt: str | None = None,
) -> WorkflowRun:
    """Start a run on the idea, once per ``idempotency_key``.

    The same key returns the run it started (``IdempotencyMismatchError`` when that run is on
    another idea). An idea with a ``queued``, ``running`` or ``awaiting_user`` run refuses a
    new one (``RunAlreadyRunningError``); a lost race on the unique index lands here too.
    A new run needs an LLM key that passed its test (``LlmNotReadyError``); the check reads
    the key row only, after the idempotency lookup so a repeated start still gets its run.
    """
    if await repo.ideas.get(session, workspace_id, idea_id) is None:
        raise IdeaNotFoundError()
    if (
        known := await _run_for_key(session, workspace_id, idea_id, idempotency_key, user_prompt)
    ) is not None:
        return known
    await _require_llm_ready(session, workspace_id)
    await _refuse_if_active(session, workspace_id, idea_id)
    row = await repo.workflow_runs.create_or_none(
        session,
        workspace_id,
        idea_id,
        kind=RunKind.PIPELINE.value,
        idempotency_key=idempotency_key,
        user_prompt=user_prompt,
    )
    if row is None:  # lost a race: the winner holds the key or the idea's active slot
        known = await _run_for_key(session, workspace_id, idea_id, idempotency_key, user_prompt)
        if known is not None:
            return known
        raise RunAlreadyRunningError()
    logger.info("run.created", run_id=str(row.id), idea_id=str(idea_id))
    return WorkflowRun.model_validate(row)


async def prepare_resume(
    session: AsyncSession, workspace_id: UUID, run_id: UUID, value: str | bool
) -> tuple[WorkflowRun, str | bool]:
    """The run and the checked value to resume it with; only an ``awaiting_user`` run resumes."""
    run = await get_run(session, workspace_id, run_id)
    if run.status != RunStatus.AWAITING_USER:
        raise IllegalRunTransition(f"A run that is {run.status.value} cannot be resumed")
    return run, check_resume_value(run.pending_interrupt, value)


async def cancel_run(session: AsyncSession, workspace_id: UUID, run_id: UUID) -> WorkflowRun:
    """Cancel a ``queued`` or ``awaiting_user`` run now; a ``running`` one is returned as is.

    The caller sets the cancel flag so the worker stops a ``running`` run. A cancelled run
    stays cancelled; any other terminal run is ``IllegalRunTransition``.
    """
    run = await get_run(session, workspace_id, run_id)
    if run.status == RunStatus.CANCELLED or run.status == RunStatus.RUNNING:
        return run
    if run.status in TERMINAL_STATUSES:
        raise IllegalRunTransition(f"A run that is {run.status.value} cannot be cancelled")
    try:
        return await mark_cancelled(session, workspace_id, run_id)
    except RunNotFoundError:  # the worker picked it up first: it is running now
        return await get_run(session, workspace_id, run_id)


async def get_run_view(session: AsyncSession, workspace_id: UUID, run_id: UUID) -> RunView:
    """The run with its idea's stage; a run of an archived idea is ``RunNotFoundError``."""
    run = await get_run(session, workspace_id, run_id)
    idea = await repo.ideas.get(session, workspace_id, run.idea_id)
    if idea is None:
        raise RunNotFoundError()
    return _view(run, idea.stage)


async def list_runs(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> RunPage:
    """One page of the idea's runs, newest first, resuming after ``cursor``."""
    idea = await repo.ideas.get(session, workspace_id, idea_id)
    if idea is None:
        raise IdeaNotFoundError()
    after = decode_cursor(cursor) if cursor is not None else None
    rows = await repo.workflow_runs.list_page(
        session, workspace_id, idea_id, after=after, limit=limit + 1
    )
    page = rows[:limit]
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if len(rows) > limit else None
    items = [_view(WorkflowRun.model_validate(row), idea.stage) for row in page]
    return RunPage(items=items, next_cursor=next_cursor)


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


def _view(run: WorkflowRun, stage: str) -> RunView:
    return RunView.model_validate({**run.model_dump(), "stage": stage})


async def _run_for_key(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    idempotency_key: str,
    user_prompt: str | None,
) -> WorkflowRun | None:
    row = await repo.workflow_runs.get_by_key(session, workspace_id, idempotency_key)
    if row is None:
        return None
    if row.idea_id != idea_id or row.user_prompt != user_prompt:
        raise IdempotencyMismatchError()
    return WorkflowRun.model_validate(row)


async def _require_llm_ready(session: AsyncSession, workspace_id: UUID) -> None:
    readiness = await identity.key_readiness(session, workspace_id, identity.ProviderKind.LLM)
    if readiness is not identity.KeyReadiness.READY:
        raise LlmNotReadyError(_LLM_NOT_READY_TEXT[readiness], meta={"reason": readiness.value})


async def _refuse_if_active(session: AsyncSession, workspace_id: UUID, idea_id: UUID) -> None:
    active = tuple(status.value for status in ACTIVE_STATUSES)
    if await repo.workflow_runs.get_active_for_idea(session, workspace_id, idea_id, active):
        raise RunAlreadyRunningError()


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
