"""Postgres access for ``planning.task_deps``. Queries only; no business rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from metis.modules.planning.models import TaskDepRow

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID


async def create_many(
    session: AsyncSession,
    workspace_id: UUID,
    plan_id: UUID,
    pairs: Sequence[tuple[UUID, UUID]],
) -> None:
    """Insert dependencies given as ``(task_id, blocked_by_task_id)``."""
    if pairs:
        await session.execute(
            insert(TaskDepRow),
            [
                {
                    "workspace_id": workspace_id,
                    "plan_id": plan_id,
                    "task_id": task_id,
                    "blocked_by_task_id": blocker,
                }
                for task_id, blocker in pairs
            ],
        )


async def list_for_plan(
    session: AsyncSession, workspace_id: UUID, plan_id: UUID
) -> list[TaskDepRow]:
    stmt = (
        select(TaskDepRow)
        .where(TaskDepRow.workspace_id == workspace_id, TaskDepRow.plan_id == plan_id)
        .execution_options(populate_existing=True)
    )
    return list((await session.scalars(stmt)).all())


async def remove_for_plan(session: AsyncSession, workspace_id: UUID, plan_id: UUID) -> None:
    await session.execute(
        delete(TaskDepRow).where(
            TaskDepRow.workspace_id == workspace_id, TaskDepRow.plan_id == plan_id
        )
    )
