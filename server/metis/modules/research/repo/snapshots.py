"""Postgres access for ``research.snapshots``. Queries only; no business rules.

Every query filters by ``workspace_id`` as well as relying on RLS.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.db import insert_or_none
from metis.helpers.ids import uuid7
from metis.modules.research.models import SnapshotRow

if TYPE_CHECKING:
    from uuid import UUID


async def create_open_or_none(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, run_id: UUID
) -> SnapshotRow | None:
    """A new open snapshot; ``None`` when the run already has one (unique index)."""
    stmt = (
        insert(SnapshotRow)
        .values(id=uuid7(), workspace_id=workspace_id, idea_id=idea_id, run_id=run_id)
        .returning(SnapshotRow)
    )
    return await insert_or_none(session, stmt)


async def get_open_for_run(
    session: AsyncSession, workspace_id: UUID, run_id: UUID
) -> SnapshotRow | None:
    stmt = select(SnapshotRow).where(
        SnapshotRow.workspace_id == workspace_id,
        SnapshotRow.run_id == run_id,
        SnapshotRow.closed_at.is_(None),
    )
    return (await session.scalars(stmt.execution_options(populate_existing=True))).one_or_none()


async def get(
    session: AsyncSession, workspace_id: UUID, snapshot_id: UUID, *, for_share: bool = False
) -> SnapshotRow | None:
    """The snapshot; ``for_share`` locks it so it cannot close while the caller writes to it."""
    stmt = select(SnapshotRow).where(
        SnapshotRow.workspace_id == workspace_id, SnapshotRow.id == snapshot_id
    )
    if for_share:
        stmt = stmt.with_for_update(read=True)
    return (await session.scalars(stmt.execution_options(populate_existing=True))).one_or_none()


async def close(
    session: AsyncSession, workspace_id: UUID, snapshot_id: UUID, summary: str
) -> SnapshotRow | None:
    """Close a still-open snapshot; ``None`` when it is already closed or unknown."""
    stmt = (
        update(SnapshotRow)
        .where(
            SnapshotRow.workspace_id == workspace_id,
            SnapshotRow.id == snapshot_id,
            SnapshotRow.closed_at.is_(None),
        )
        .values(summary=summary, closed_at=func.now())
        .returning(SnapshotRow)
    )
    return (await session.scalars(stmt)).one_or_none()


async def latest_closed(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID
) -> SnapshotRow | None:
    stmt = (
        select(SnapshotRow)
        .where(
            SnapshotRow.workspace_id == workspace_id,
            SnapshotRow.idea_id == idea_id,
            SnapshotRow.closed_at.is_not(None),
        )
        .order_by(SnapshotRow.closed_at.desc(), SnapshotRow.id.desc())
        .limit(1)
    )
    return (await session.scalars(stmt)).one_or_none()
