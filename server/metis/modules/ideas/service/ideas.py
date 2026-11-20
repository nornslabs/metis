"""Idea business rules: create, read, list, edit, archive and stage moves.

Every function takes the caller's ``AsyncSession``, flushes but never commits (the
caller owns the transaction) and relies on ``current_workspace`` having set the
RLS context. Every read and write is scoped to the workspace id as well.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import (
    ConflictError,
    IdeaNotFoundError,
    IdeaNotOwnerError,
    InvalidInputError,
)
from metis.core.logging import bind_context, get_logger
from metis.core.outbox import DomainEvent, DomainEventType, add_event
from metis.modules import auth
from metis.modules.ideas import repo
from metis.modules.ideas.dto import (
    DEFAULT_PAGE_SIZE,
    MAX_RAW_TEXT_LENGTH,
    MIN_RAW_TEXT_LENGTH,
    Idea,
    IdeaPage,
    IdeaPatch,
    NewIdea,
    Stage,
)
from metis.modules.ideas.helpers.cursor import decode_cursor, encode_cursor
from metis.modules.ideas.helpers.transitions import check_transition
from metis.modules.ideas.models import IdeaRow
from metis.modules.identity import MemberRole, Membership

logger = get_logger(__name__)


async def create_idea(
    session: AsyncSession, user: auth.User, membership: Membership, data: NewIdea
) -> Idea:
    """Save a new idea at stage ``intake`` and record ``IdeaSubmitted`` in the same transaction."""
    workspace_id = membership.workspace.id
    row = await repo.ideas.create(
        session,
        workspace_id,
        user.id,
        title=data.title,
        raw_text=data.raw_text,
        kind=data.kind.value if data.kind else None,
    )
    add_event(
        session,
        DomainEvent(
            workspace_id=workspace_id,
            type=DomainEventType.IDEA_SUBMITTED,
            payload={"idea_id": str(row.id), "created_by": str(user.id)},
        ),
    )
    bind_context(idea_id=str(row.id))
    logger.info("idea.created", idea_id=str(row.id))
    return Idea.model_validate(row)


async def get_idea(session: AsyncSession, workspace_id: UUID, idea_id: UUID) -> Idea:
    """The idea; unknown, archived or foreign ideas are ``IdeaNotFoundError``."""
    return Idea.model_validate(await _get_row(session, workspace_id, idea_id))


async def list_ideas(
    session: AsyncSession,
    workspace_id: UUID,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> IdeaPage:
    """One page of the workspace's ideas, newest first, resuming after ``cursor``."""
    after = decode_cursor(cursor) if cursor is not None else None
    rows = await repo.ideas.list_page(session, workspace_id, after=after, limit=limit + 1)
    page = rows[:limit]
    has_more = len(rows) > limit
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if has_more else None
    return IdeaPage(items=[Idea.model_validate(row) for row in page], next_cursor=next_cursor)


async def update_idea(
    session: AsyncSession,
    user: auth.User,
    membership: Membership,
    idea_id: UUID,
    patch: IdeaPatch,
) -> Idea:
    """Apply ``patch`` if ``patch.version`` is current; stale is ``ConflictError`` (409).

    Only the idea's creator or a workspace owner may edit it.
    """
    workspace_id = membership.workspace.id
    row = await _get_row(session, workspace_id, idea_id)
    _require_creator_or_owner(user, membership, row)
    updated = await repo.ideas.update_at_version(
        session, workspace_id, idea_id, version=patch.version, changes=patch.changes
    )
    if updated is None:
        await _get_row(session, workspace_id, idea_id)  # gone meanwhile: 404, not 409
        raise ConflictError("The idea changed since you loaded it; reload and try again")
    return Idea.model_validate(updated)


async def archive_idea(
    session: AsyncSession, user: auth.User, membership: Membership, idea_id: UUID
) -> None:
    """Soft-archive the idea (creator or workspace owner only); it is then hidden everywhere."""
    workspace_id = membership.workspace.id
    row = await _get_row(session, workspace_id, idea_id)
    _require_creator_or_owner(user, membership, row)
    if not await repo.ideas.archive(session, workspace_id, idea_id):
        raise IdeaNotFoundError("Idea not found")
    logger.info("idea.archived", idea_id=str(idea_id))


async def transition(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, to_stage: Stage
) -> Idea:
    """Move the idea to ``to_stage``; a move not in the table is ``IllegalTransition`` (409)."""
    row = await _get_row(session, workspace_id, idea_id)
    check_transition(Stage(row.stage), to_stage)
    updated = await repo.ideas.update_at_version(
        session, workspace_id, idea_id, version=row.version, changes={"stage": to_stage.value}
    )
    if updated is None:
        raise ConflictError("The idea changed while its stage was being moved; try again")
    return Idea.model_validate(updated)


async def apply_revision(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, raw_text: str
) -> Idea:
    """Replace the idea's text with the user's revision (the Advisor's write, on resume).

    Same bounds as an idea's text. Writing the text the idea already has changes nothing, so a
    node re-run after a crash is safe. Bumps ``version`` when the text changes.
    """
    text = raw_text.strip()
    if not MIN_RAW_TEXT_LENGTH <= len(text) <= MAX_RAW_TEXT_LENGTH:
        raise InvalidInputError(
            "Invalid idea text",
            errors=[
                {
                    "field": "raw_text",
                    "message": f"{MIN_RAW_TEXT_LENGTH} to {MAX_RAW_TEXT_LENGTH} characters",
                }
            ],
        )
    row = await _get_row(session, workspace_id, idea_id)
    if row.raw_text == text:
        return Idea.model_validate(row)
    updated = await repo.ideas.update_at_version(
        session, workspace_id, idea_id, version=row.version, changes={"raw_text": text}
    )
    if updated is None:
        raise ConflictError("The idea changed while the revision was saved; try again")
    logger.info("idea.revised", idea_id=str(idea_id))
    return Idea.model_validate(updated)


async def set_current_score(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, score: int
) -> None:
    """Record the idea's latest total (0–100); it is the scoring module's write.

    Does not bump ``version`` or move the stage. Unknown or archived idea → ``IdeaNotFoundError``.
    """
    if not await repo.ideas.set_current_score(session, workspace_id, idea_id, score):
        raise IdeaNotFoundError("Idea not found")


async def _get_row(session: AsyncSession, workspace_id: UUID, idea_id: UUID) -> IdeaRow:
    row = await repo.ideas.get(session, workspace_id, idea_id)
    if row is None:
        raise IdeaNotFoundError("Idea not found")
    bind_context(idea_id=str(idea_id))
    return row


def _require_creator_or_owner(user: auth.User, membership: Membership, row: IdeaRow) -> None:
    if row.created_by != user.id and membership.role is not MemberRole.OWNER:
        raise IdeaNotOwnerError("Only the idea's creator or a workspace owner can change it")
