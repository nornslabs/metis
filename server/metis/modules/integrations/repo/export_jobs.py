"""Postgres access for ``integrations.export_jobs``. Queries only; no business rules."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.helpers.ids import uuid7
from metis.modules.integrations.models import ExportJobRow


async def get_by_run(
    session: AsyncSession, workspace_id: UUID, run_id: UUID
) -> ExportJobRow | None:
    return await session.scalar(
        select(ExportJobRow).where(
            ExportJobRow.workspace_id == workspace_id, ExportJobRow.run_id == run_id
        )
    )


async def create_once(
    session: AsyncSession,
    workspace_id: UUID,
    *,
    idea_id: UUID,
    plan_id: UUID,
    run_id: UUID,
    provider: str,
    status: str,
    summary: dict[str, Any],
    decided_by: UUID,
    decided_at: datetime,
) -> ExportJobRow | None:
    """Insert the run's job; ``None`` when the run already has one (nothing changes)."""
    stmt = (
        insert(ExportJobRow)
        .values(
            id=uuid7(),
            workspace_id=workspace_id,
            idea_id=idea_id,
            plan_id=plan_id,
            run_id=run_id,
            provider=provider,
            status=status,
            summary=summary,
            decided_by=decided_by,
            decided_at=decided_at,
        )
        .on_conflict_do_nothing(index_elements=[ExportJobRow.run_id])
        .returning(ExportJobRow)
    )
    return (await session.scalars(stmt)).one_or_none()


async def mark_running(
    session: AsyncSession, workspace_id: UUID, run_id: UUID, *, from_status: str, to_status: str
) -> ExportJobRow | None:
    """Move the run's ``approved`` job to ``running``. A job already ``running`` is returned as
    it is; a job in any other status (or none) is ``None`` and nothing changes."""
    result = await session.scalars(
        update(ExportJobRow)
        .where(
            ExportJobRow.workspace_id == workspace_id,
            ExportJobRow.run_id == run_id,
            ExportJobRow.status == from_status,
        )
        .values(status=to_status)
        .returning(ExportJobRow)
    )
    row = result.one_or_none()
    if row is not None:
        return row
    current = await get_by_run(session, workspace_id, run_id)
    return current if current is not None and current.status == to_status else None


async def mark_finished(
    session: AsyncSession,
    workspace_id: UUID,
    run_id: UUID,
    *,
    status: str,
    summary: dict[str, Any],
    finished_at: datetime,
) -> ExportJobRow | None:
    """End the run's ``running`` job with ``status`` and ``summary``. ``None`` when the job is not
    ``running`` (already ended, or never started) and nothing changes."""
    result = await session.scalars(
        update(ExportJobRow)
        .where(
            ExportJobRow.workspace_id == workspace_id,
            ExportJobRow.run_id == run_id,
            ExportJobRow.status == "running",
        )
        .values(status=status, summary=summary, finished_at=finished_at)
        .returning(ExportJobRow)
    )
    return result.one_or_none()
