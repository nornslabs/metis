"""Postgres access for ``research.idea_competitors``. Queries only; no business rules.

Every query filters by ``workspace_id`` as well as relying on RLS.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.modules.research.models import CompetitorRow, IdeaCompetitorRow

if TYPE_CHECKING:
    from uuid import UUID


async def upsert(
    session: AsyncSession,
    workspace_id: UUID,
    *,
    snapshot_id: UUID,
    idea_id: UUID,
    competitor_id: UUID,
    overlap: float,
) -> None:
    """Link the competitor to the snapshot; a repeat link replaces the overlap."""
    stmt = insert(IdeaCompetitorRow).values(
        workspace_id=workspace_id,
        snapshot_id=snapshot_id,
        idea_id=idea_id,
        competitor_id=competitor_id,
        overlap=Decimal(str(overlap)),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[IdeaCompetitorRow.snapshot_id, IdeaCompetitorRow.competitor_id],
        set_={"overlap": stmt.excluded.overlap},
    )
    await session.execute(stmt)


async def list_for_snapshot(
    session: AsyncSession, workspace_id: UUID, snapshot_id: UUID
) -> list[tuple[CompetitorRow, Decimal]]:
    """The snapshot's competitors with their overlap, most overlap first, then by name."""
    stmt = (
        select(CompetitorRow, IdeaCompetitorRow.overlap)
        .join(IdeaCompetitorRow, IdeaCompetitorRow.competitor_id == CompetitorRow.id)
        .where(
            IdeaCompetitorRow.workspace_id == workspace_id,
            IdeaCompetitorRow.snapshot_id == snapshot_id,
        )
        .order_by(
            IdeaCompetitorRow.overlap.desc(), func.lower(CompetitorRow.name), CompetitorRow.id
        )
    )
    return [(row, overlap) for row, overlap in (await session.execute(stmt)).all()]
