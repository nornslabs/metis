"""Postgres access for ``scoring.score_runs``. Queries only; no business rules.

Every query filters by ``workspace_id`` as well as relying on RLS. Runs are ordered by their
uuid7 ``id``. There is no update or delete: score runs are immutable.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.helpers.ids import uuid7
from metis.modules.scoring.models import ScoreRunRow


async def lock_idea(session: AsyncSession, idea_id: UUID) -> None:
    """Serialize scorers of one idea until the transaction ends (advisory lock on its id)."""
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(str(idea_id), 0)))
    )


async def create(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    run_id: UUID,
    *,
    rubric_version_id: int,
    trigger: str,
    total: int,
    band: str,
) -> ScoreRunRow:
    stmt = (
        insert(ScoreRunRow)
        .values(
            id=uuid7(),
            workspace_id=workspace_id,
            idea_id=idea_id,
            run_id=run_id,
            rubric_version_id=rubric_version_id,
            trigger=trigger,
            total=total,
            band=band,
        )
        .returning(ScoreRunRow)
    )
    return (await session.scalars(stmt)).one()


async def get(session: AsyncSession, workspace_id: UUID, score_run_id: UUID) -> ScoreRunRow | None:
    stmt = select(ScoreRunRow).where(
        ScoreRunRow.workspace_id == workspace_id, ScoreRunRow.id == score_run_id
    )
    return (await session.scalars(stmt)).one_or_none()


async def latest_for_idea(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID
) -> ScoreRunRow | None:
    stmt = (
        select(ScoreRunRow)
        .where(ScoreRunRow.workspace_id == workspace_id, ScoreRunRow.idea_id == idea_id)
        .order_by(ScoreRunRow.id.desc())
        .limit(1)
    )
    return (await session.scalars(stmt)).one_or_none()


async def list_for_idea(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID
) -> list[ScoreRunRow]:
    """The idea's score runs, newest first."""
    stmt = (
        select(ScoreRunRow)
        .where(ScoreRunRow.workspace_id == workspace_id, ScoreRunRow.idea_id == idea_id)
        .order_by(ScoreRunRow.id.desc())
    )
    return list((await session.scalars(stmt)).all())
