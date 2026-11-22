"""Postgres access for ``planning.tasks``. Queries only; no business rules."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from metis.modules.planning.models import TaskRow


async def create_many(
    session: AsyncSession, workspace_id: UUID, plan_id: UUID, rows: Sequence[dict[str, Any]]
) -> None:
    """Insert tasks given as column dicts; they may point at each other (one statement)."""
    if rows:
        await session.execute(
            insert(TaskRow),
            [{**row, "workspace_id": workspace_id, "plan_id": plan_id} for row in rows],
        )


async def list_for_plan(session: AsyncSession, workspace_id: UUID, plan_id: UUID) -> list[TaskRow]:
    stmt = (
        select(TaskRow)
        .where(TaskRow.workspace_id == workspace_id, TaskRow.plan_id == plan_id)
        .order_by(TaskRow.position)
        .execution_options(populate_existing=True)
    )
    return list((await session.scalars(stmt)).all())


async def get(
    session: AsyncSession, workspace_id: UUID, plan_id: UUID, task_id: UUID
) -> TaskRow | None:
    stmt = (
        select(TaskRow)
        .where(
            TaskRow.workspace_id == workspace_id,
            TaskRow.plan_id == plan_id,
            TaskRow.id == task_id,
        )
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one_or_none()


async def update_one(
    session: AsyncSession, workspace_id: UUID, task_id: UUID, values: dict[str, Any]
) -> None:
    await session.execute(
        update(TaskRow)
        .where(TaskRow.workspace_id == workspace_id, TaskRow.id == task_id)
        .values(**values)
    )


async def remove_for_plan(session: AsyncSession, workspace_id: UUID, plan_id: UUID) -> None:
    await session.execute(
        delete(TaskRow).where(TaskRow.workspace_id == workspace_id, TaskRow.plan_id == plan_id)
    )
