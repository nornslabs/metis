"""Postgres access for ``scoring.suggestions``. Queries only; no business rules.

Every query filters by ``workspace_id`` as well as relying on RLS. A suggestion's text is
immutable (the app role may update ``status`` only); there is no delete.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.helpers.ids import uuid7
from metis.modules.scoring.models import SuggestionRow


async def create(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    score_run_id: UUID,
    values: dict[str, Any],
) -> SuggestionRow:
    stmt = (
        insert(SuggestionRow)
        .values(
            id=uuid7(),
            workspace_id=workspace_id,
            idea_id=idea_id,
            score_run_id=score_run_id,
            **values,
        )
        .returning(SuggestionRow)
    )
    return (await session.scalars(stmt)).one()


async def get(
    session: AsyncSession, workspace_id: UUID, suggestion_id: UUID
) -> SuggestionRow | None:
    stmt = select(SuggestionRow).where(
        SuggestionRow.workspace_id == workspace_id, SuggestionRow.id == suggestion_id
    )
    return (await session.scalars(stmt)).one_or_none()


async def list_for_idea(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    score_run_id: UUID | None = None,
) -> list[SuggestionRow]:
    """Newest score run first (uuid7 order), then in the order saved."""
    stmt = select(SuggestionRow).where(
        SuggestionRow.workspace_id == workspace_id, SuggestionRow.idea_id == idea_id
    )
    if score_run_id is not None:
        stmt = stmt.where(SuggestionRow.score_run_id == score_run_id)
    stmt = stmt.order_by(SuggestionRow.score_run_id.desc(), SuggestionRow.id.asc())
    return list((await session.scalars(stmt)).all())


async def set_status(
    session: AsyncSession, workspace_id: UUID, suggestion_id: UUID, status: str
) -> SuggestionRow | None:
    stmt = (
        update(SuggestionRow)
        .where(SuggestionRow.workspace_id == workspace_id, SuggestionRow.id == suggestion_id)
        .values(status=status)
        .returning(SuggestionRow)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one_or_none()
