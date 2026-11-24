"""Postgres access for ``planning.phases``. Queries only; no business rules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from metis.modules.planning.models import PhaseRow

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID


async def create_many(
    session: AsyncSession, workspace_id: UUID, plan_id: UUID, rows: Sequence[dict[str, Any]]
) -> None:
    """Insert phases given as ``{id, position, name, goal, exit_criteria}``."""
    if rows:
        await session.execute(
            insert(PhaseRow),
            [{**row, "workspace_id": workspace_id, "plan_id": plan_id} for row in rows],
        )


async def list_for_plan(session: AsyncSession, workspace_id: UUID, plan_id: UUID) -> list[PhaseRow]:
    stmt = (
        select(PhaseRow)
        .where(PhaseRow.workspace_id == workspace_id, PhaseRow.plan_id == plan_id)
        .order_by(PhaseRow.position)
        .execution_options(populate_existing=True)
    )
    return list((await session.scalars(stmt)).all())


async def update_one(
    session: AsyncSession, workspace_id: UUID, phase_id: UUID, values: dict[str, Any]
) -> None:
    await session.execute(
        update(PhaseRow)
        .where(PhaseRow.workspace_id == workspace_id, PhaseRow.id == phase_id)
        .values(**values)
    )


async def remove_many(session: AsyncSession, workspace_id: UUID, phase_ids: Sequence[UUID]) -> None:
    if phase_ids:
        await session.execute(
            delete(PhaseRow).where(
                PhaseRow.workspace_id == workspace_id, PhaseRow.id.in_(phase_ids)
            )
        )


async def remove_for_plan(session: AsyncSession, workspace_id: UUID, plan_id: UUID) -> None:
    await session.execute(
        delete(PhaseRow).where(PhaseRow.workspace_id == workspace_id, PhaseRow.plan_id == plan_id)
    )
