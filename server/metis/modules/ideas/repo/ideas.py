"""Postgres access for ``ideas.ideas``. Queries only; no business rules.

Every query filters by ``workspace_id`` as well as relying on RLS, so a missing
RLS context can never widen a read. Archived ideas are never returned.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.helpers.ids import uuid7
from metis.modules.ideas.models import IdeaRow


async def create(
    session: AsyncSession,
    workspace_id: UUID,
    created_by: UUID,
    *,
    title: str,
    raw_text: str,
    kind: str | None,
) -> IdeaRow:
    stmt = (
        insert(IdeaRow)
        .values(
            id=uuid7(),
            workspace_id=workspace_id,
            created_by=created_by,
            title=title,
            raw_text=raw_text,
            kind=kind,
        )
        .returning(IdeaRow)
    )
    return (await session.scalars(stmt)).one()


async def get(session: AsyncSession, workspace_id: UUID, idea_id: UUID) -> IdeaRow | None:
    stmt = select(IdeaRow).where(
        IdeaRow.id == idea_id,
        IdeaRow.workspace_id == workspace_id,
        IdeaRow.archived_at.is_(None),
    )
    return (await session.scalars(stmt.execution_options(populate_existing=True))).one_or_none()


async def list_page(
    session: AsyncSession,
    workspace_id: UUID,
    *,
    after: tuple[datetime, UUID] | None,
    limit: int,
    title_contains: str | None = None,
    stages: Sequence[str] | None = None,
    scored_only: bool = False,
) -> list[IdeaRow]:
    """Up to ``limit`` ideas, most recently active first, strictly after ``after``.

    ``title_contains`` is a case-insensitive literal substring; ``stages`` keeps only those
    stages; ``scored_only`` keeps ideas with a current score.
    """
    stmt = select(IdeaRow).where(
        IdeaRow.workspace_id == workspace_id, IdeaRow.archived_at.is_(None)
    )
    if title_contains is not None:
        stmt = stmt.where(IdeaRow.title.icontains(title_contains, autoescape=True))
    if stages is not None:
        stmt = stmt.where(IdeaRow.stage.in_(stages))
    if scored_only:
        stmt = stmt.where(IdeaRow.current_score.is_not(None))
    if after is not None:
        stmt = stmt.where(tuple_(IdeaRow.updated_at, IdeaRow.id) < tuple_(*after))
    stmt = stmt.order_by(IdeaRow.updated_at.desc(), IdeaRow.id.desc()).limit(limit)
    return list((await session.scalars(stmt)).all())


async def live_ids(
    session: AsyncSession, workspace_id: UUID, idea_ids: Sequence[UUID]
) -> set[UUID]:
    """The ids among ``idea_ids`` that are unarchived ideas of the workspace."""
    stmt = select(IdeaRow.id).where(
        IdeaRow.workspace_id == workspace_id,
        IdeaRow.archived_at.is_(None),
        IdeaRow.id.in_(idea_ids),
    )
    return set((await session.scalars(stmt)).all())


async def touch(session: AsyncSession, workspace_id: UUID, idea_id: UUID) -> None:
    """Mark activity on the idea (``updated_at`` only; ``version`` is not bumped)."""
    await session.execute(
        update(IdeaRow)
        .where(IdeaRow.id == idea_id, IdeaRow.workspace_id == workspace_id)
        .values(updated_at=func.now())
    )


async def update_at_version(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    *,
    version: int,
    changes: dict[str, object],
) -> IdeaRow | None:
    """Apply ``changes`` if the idea is still at ``version``; ``None`` on a mismatch."""
    stmt = (
        update(IdeaRow)
        .where(
            IdeaRow.id == idea_id,
            IdeaRow.workspace_id == workspace_id,
            IdeaRow.version == version,
            IdeaRow.archived_at.is_(None),
        )
        .values(**changes, version=IdeaRow.version + 1, updated_at=func.now())
        .returning(IdeaRow)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one_or_none()


async def archive(session: AsyncSession, workspace_id: UUID, idea_id: UUID) -> bool:
    """Archive the idea; ``False`` if it does not exist or is already archived."""
    stmt = (
        update(IdeaRow)
        .where(
            IdeaRow.id == idea_id,
            IdeaRow.workspace_id == workspace_id,
            IdeaRow.archived_at.is_(None),
        )
        .values(archived_at=func.now(), version=IdeaRow.version + 1, updated_at=func.now())
        .returning(IdeaRow.id)
    )
    return (await session.scalars(stmt)).one_or_none() is not None


async def set_interview_brief(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, brief: dict[str, Any]
) -> bool:
    """Store the idea's interview brief; ``False`` when no such (unarchived) idea.

    ``version`` is not bumped: the brief is the agent's output, and a user's edit of the
    title or text must not conflict with it.
    """
    stmt = (
        update(IdeaRow)
        .where(
            IdeaRow.id == idea_id,
            IdeaRow.workspace_id == workspace_id,
            IdeaRow.archived_at.is_(None),
        )
        .values(interview_brief=brief)
        .returning(IdeaRow.id)
    )
    return (await session.scalars(stmt)).one_or_none() is not None


async def set_current_score(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, score: int
) -> bool:
    """Store the idea's current score; ``False`` when no such (unarchived) idea.

    ``updated_at`` moves (last activity) but ``version`` is not bumped: the score is the
    scorer's output, and a user's edit of the title or text must not conflict with it.
    """
    stmt = (
        update(IdeaRow)
        .where(
            IdeaRow.id == idea_id,
            IdeaRow.workspace_id == workspace_id,
            IdeaRow.archived_at.is_(None),
        )
        .values(current_score=score, updated_at=func.now())
        .returning(IdeaRow.id)
    )
    return (await session.scalars(stmt)).one_or_none() is not None


async def set_kind_if_null(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, kind: str
) -> bool:
    """Set ``kind`` only while the idea has none; ``False`` when no such idea or already set.

    ``version`` is not bumped: it is the Architect's default, not a user edit.
    """
    stmt = (
        update(IdeaRow)
        .where(
            IdeaRow.id == idea_id,
            IdeaRow.workspace_id == workspace_id,
            IdeaRow.archived_at.is_(None),
            IdeaRow.kind.is_(None),
        )
        .values(kind=kind)
        .returning(IdeaRow.id)
    )
    return (await session.scalars(stmt)).one_or_none() is not None


async def set_confirmed_spec(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, version_id: UUID
) -> None:
    """Point the idea at the spec version the user confirmed."""
    stmt = (
        update(IdeaRow)
        .where(IdeaRow.id == idea_id, IdeaRow.workspace_id == workspace_id)
        .values(confirmed_spec_version_id=version_id)
    )
    await session.execute(stmt)
