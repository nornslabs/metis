"""Postgres access for ``ideas.ideas``. Queries only; no business rules.

Every query filters by ``workspace_id`` as well as relying on RLS, so a missing
RLS context can never widen a read. Archived ideas are never returned.
"""

from __future__ import annotations

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
) -> list[IdeaRow]:
    """Up to ``limit`` ideas, newest first, strictly after the ``after`` position."""
    stmt = select(IdeaRow).where(
        IdeaRow.workspace_id == workspace_id, IdeaRow.archived_at.is_(None)
    )
    if after is not None:
        stmt = stmt.where(tuple_(IdeaRow.created_at, IdeaRow.id) < tuple_(*after))
    stmt = stmt.order_by(IdeaRow.created_at.desc(), IdeaRow.id.desc()).limit(limit)
    return list((await session.scalars(stmt)).all())


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

    ``version`` is not bumped: the score is the scorer's output, and a user's edit of the
    title or text must not conflict with it.
    """
    stmt = (
        update(IdeaRow)
        .where(
            IdeaRow.id == idea_id,
            IdeaRow.workspace_id == workspace_id,
            IdeaRow.archived_at.is_(None),
        )
        .values(current_score=score)
        .returning(IdeaRow.id)
    )
    return (await session.scalars(stmt)).one_or_none() is not None
