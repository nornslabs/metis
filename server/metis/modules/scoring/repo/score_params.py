"""Postgres access for ``scoring.score_params``. Queries only; no business rules.

Rows are only ever inserted, together with their score run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.modules.scoring.models import ScoreParamRow

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID


async def create_many(
    session: AsyncSession,
    workspace_id: UUID,
    score_run_id: UUID,
    rows: Sequence[dict[str, Any]],
) -> list[ScoreParamRow]:
    """Insert one row per entry of ``rows`` (``param``, ``raw``, ``weighted``, …)."""
    stmt = (
        insert(ScoreParamRow)
        .values([{"workspace_id": workspace_id, "score_run_id": score_run_id, **r} for r in rows])
        .returning(ScoreParamRow)
    )
    return list((await session.scalars(stmt)).all())


async def list_for_run(
    session: AsyncSession, workspace_id: UUID, score_run_id: UUID
) -> list[ScoreParamRow]:
    stmt = select(ScoreParamRow).where(
        ScoreParamRow.workspace_id == workspace_id, ScoreParamRow.score_run_id == score_run_id
    )
    return list((await session.scalars(stmt)).all())
