"""Spec versions: save (agent draft or user edit), read, compare and confirm.

Every function takes the caller's ``AsyncSession``, flushes but never commits, and is scoped to
the workspace id as well as RLS. Versions are immutable and numbered per idea from 1; writers of
one idea take an advisory lock, so two edits can never get the same number. An edit names the
version it was made from (``base_number``) and a stale one is ``SpecConflictError`` (409).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.agent.tools.ask_user import SPEC_REVIEW
from metis.core.errors import (
    IdeaNotFoundError,
    InvalidInputError,
    SpecConflictError,
    SpecNotEditableError,
    SpecNotFoundError,
)
from metis.core.logging import get_logger
from metis.core.outbox import DomainEvent, DomainEventType, add_event
from metis.modules.ideas import repo
from metis.modules.ideas.dto import (
    MAX_SPEC_LENGTH,
    Idea,
    NewSpecVersion,
    RunStatus,
    SpecDiff,
    SpecOverview,
    SpecSource,
    SpecVersion,
    SpecVersionList,
    SpecVersionSummary,
    Stage,
    WorkflowRun,
)
from metis.modules.ideas.dto.ideas import IdeaKind
from metis.modules.ideas.helpers.spec_markdown import diff_sections, parse_sections
from metis.modules.ideas.models import IdeaRow, SpecVersionRow
from metis.modules.ideas.service import ideas as ideas_service

logger = get_logger(__name__)

_WAITING = (RunStatus.AWAITING_USER.value,)


async def save_spec_version(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    data: NewSpecVersion,
    base_number: int | None = None,
) -> SpecVersion:
    """Save the next version of the idea's spec.

    A ``user`` version needs ``base_number``: the idea must have a spec, be at ``spec_draft``
    and ``base_number`` must be the latest version, else ``SpecNotFoundError``,
    ``SpecNotEditableError`` or ``SpecConflictError``. An ``agent`` version returns the run's
    existing draft unchanged, so a node re-run adds nothing.
    """
    content = _checked_text(data.content_md)
    await repo.specs.lock_idea(session, idea_id)  # before reading the idea: its stage may move
    idea = await _get_idea_row(session, workspace_id, idea_id)
    if data.source is SpecSource.AGENT and data.run_id is not None:
        existing = await repo.specs.get_agent_draft(session, workspace_id, data.run_id)
        if existing is not None:
            return SpecVersion.model_validate(existing)
    latest = await repo.specs.latest(session, workspace_id, idea_id)
    if data.source is SpecSource.USER:
        _check_edit(idea, latest, base_number)
    number = 1 if latest is None else latest.number + 1
    row = await repo.specs.create(
        session,
        workspace_id,
        idea_id,
        number=number,
        source=data.source.value,
        content_md=content,
        sections=data.sections if data.sections is not None else parse_sections(content),
        run_id=data.run_id,
        created_by=data.created_by,
    )
    logger.info("spec.version_saved", idea_id=str(idea_id), number=number, source=data.source.value)
    return SpecVersion.model_validate(row)


async def get_spec(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, number: int | None = None
) -> SpecVersion:
    """The version ``number``, or the latest; none is ``SpecNotFoundError``."""
    await _get_idea_row(session, workspace_id, idea_id)
    row = await _find(session, workspace_id, idea_id, number)
    return SpecVersion.model_validate(row)


async def get_spec_overview(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID
) -> SpecOverview:
    """The latest and the confirmed version; each is ``None`` while there is none."""
    idea = await _get_idea_row(session, workspace_id, idea_id)
    latest = await repo.specs.latest(session, workspace_id, idea_id)
    confirmed = None
    if idea.confirmed_spec_version_id is not None:
        confirmed = await repo.specs.get(session, workspace_id, idea.confirmed_spec_version_id)
    return SpecOverview(
        latest=None if latest is None else SpecVersion.model_validate(latest),
        confirmed=None if confirmed is None else SpecVersion.model_validate(confirmed),
    )


async def list_spec_versions(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID
) -> SpecVersionList:
    """The idea's versions without their text, newest first."""
    await _get_idea_row(session, workspace_id, idea_id)
    rows = await repo.specs.list_for_idea(session, workspace_id, idea_id)
    return SpecVersionList(items=[SpecVersionSummary.model_validate(row) for row in rows])


async def diff_specs(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, a: int, b: int
) -> SpecDiff:
    """Section by section, what changed from version ``a`` to version ``b``."""
    await _get_idea_row(session, workspace_id, idea_id)
    first = await _find(session, workspace_id, idea_id, a)
    second = await _find(session, workspace_id, idea_id, b)
    return SpecDiff(a=a, b=b, sections=diff_sections(first.sections, second.sections))


async def confirm_spec(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, number: int
) -> Idea:
    """Confirm version ``number``: it must be the latest and the idea at ``spec_draft``.

    Fixes the version on the idea, moves the stage to ``spec_confirmed`` and records
    ``SpecConfirmed`` in the same transaction. Confirming the version already confirmed is a
    no-op (no second event).
    """
    await repo.specs.lock_idea(session, idea_id)  # before reading the idea: its stage may move
    idea = await _get_idea_row(session, workspace_id, idea_id)
    latest = await repo.specs.latest(session, workspace_id, idea_id)
    if latest is None:
        raise SpecNotFoundError("The idea has no spec yet")
    if number != latest.number:
        raise SpecConflictError("A newer version exists; review the latest one before confirming")
    if idea.stage == Stage.SPEC_CONFIRMED and idea.confirmed_spec_version_id == latest.id:
        return Idea.model_validate(idea)
    if idea.stage != Stage.SPEC_DRAFT:
        raise SpecNotEditableError("The spec can be confirmed only while it is a draft")
    confirmed = await ideas_service.transition(session, workspace_id, idea_id, Stage.SPEC_CONFIRMED)
    await repo.ideas.set_confirmed_spec(session, workspace_id, idea_id, latest.id)
    add_event(
        session,
        DomainEvent(
            workspace_id=workspace_id,
            type=DomainEventType.SPEC_CONFIRMED,
            payload={
                "idea_id": str(idea_id),
                "spec_version_id": str(latest.id),
                "number": latest.number,
            },
        ),
    )
    logger.info("spec.confirmed", idea_id=str(idea_id), number=latest.number)
    return confirmed


async def waiting_run(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID
) -> WorkflowRun | None:
    """The idea's run paused on ``spec_review``, if any."""
    row = await repo.workflow_runs.get_active_for_idea(session, workspace_id, idea_id, _WAITING)
    if row is None or (row.pending_interrupt or {}).get("type") != SPEC_REVIEW:
        return None
    return WorkflowRun.model_validate(row)


async def set_kind(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, kind: IdeaKind
) -> None:
    """Give the idea a ``kind`` when it has none; a kind the user chose stays."""
    await _get_idea_row(session, workspace_id, idea_id)
    # ``False`` (a kind is already set) is the intended no-op, so the result is not checked.
    await repo.ideas.set_kind_if_null(session, workspace_id, idea_id, kind.value)


async def _get_idea_row(session: AsyncSession, workspace_id: UUID, idea_id: UUID) -> IdeaRow:
    row = await repo.ideas.get(session, workspace_id, idea_id)
    if row is None:
        raise IdeaNotFoundError("Idea not found")
    return row


async def _find(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, number: int | None
) -> SpecVersionRow:
    if number is None:
        row = await repo.specs.latest(session, workspace_id, idea_id)
    else:
        row = await repo.specs.get_by_number(session, workspace_id, idea_id, number)
    if row is None:
        raise SpecNotFoundError("Spec version not found")
    return row


def _check_edit(idea: IdeaRow, latest: SpecVersionRow | None, base_number: int | None) -> None:
    if latest is None:
        raise SpecNotFoundError("The idea has no spec yet")
    if idea.stage != Stage.SPEC_DRAFT:
        raise SpecNotEditableError("The spec can be edited only while it is a draft")
    if base_number is None:
        raise InvalidInputError(
            "Invalid spec edit",
            errors=[{"field": "base_number", "message": "name the version you edited"}],
        )
    if base_number != latest.number:
        raise SpecConflictError("The spec changed since you loaded it; reload and try again")


def _checked_text(content_md: str) -> str:
    text = content_md.strip()
    if not 1 <= len(text) <= MAX_SPEC_LENGTH:
        raise InvalidInputError(
            "Invalid spec",
            errors=[{"field": "content_md", "message": f"1 to {MAX_SPEC_LENGTH} characters"}],
        )
    return text
