"""Postgres access for ``planning.plans``. Queries only; no business rules.

Every query filters by ``workspace_id`` as well as relying on RLS.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from metis.modules.planning.dto import PlanStatus
from metis.modules.planning.models import PlanRow

if TYPE_CHECKING:
    from uuid import UUID

_LOCK_SALT = 2  # apart from the ideas module's advisory lock on the same idea id


async def lock_idea(session: AsyncSession, idea_id: UUID) -> None:
    """Serialize the writers of one idea's plans until the transaction ends (advisory lock)."""
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(str(idea_id), _LOCK_SALT)))
    )


async def create(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, spec_version_id: UUID
) -> PlanRow:
    row = PlanRow(workspace_id=workspace_id, idea_id=idea_id, spec_version_id=spec_version_id)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def get(session: AsyncSession, workspace_id: UUID, plan_id: UUID) -> PlanRow | None:
    stmt = (
        select(PlanRow)
        .where(PlanRow.workspace_id == workspace_id, PlanRow.id == plan_id)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one_or_none()


async def get_for_spec(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, spec_version_id: UUID
) -> PlanRow | None:
    stmt = (
        select(PlanRow)
        .where(
            PlanRow.workspace_id == workspace_id,
            PlanRow.idea_id == idea_id,
            PlanRow.spec_version_id == spec_version_id,
        )
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one_or_none()


async def latest_for_idea(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID
) -> PlanRow | None:
    stmt = (
        select(PlanRow)
        .where(PlanRow.workspace_id == workspace_id, PlanRow.idea_id == idea_id)
        .order_by(PlanRow.created_at.desc(), PlanRow.id.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one_or_none()


async def claim_version(
    session: AsyncSession, workspace_id: UUID, plan_id: UUID, version: int
) -> PlanRow | None:
    """Move a draft plan from ``version`` to the next; ``None`` when it is no longer there.

    The update takes the row lock, so two edits on one version cannot both succeed.
    """
    stmt = (
        update(PlanRow)
        .where(
            PlanRow.workspace_id == workspace_id,
            PlanRow.id == plan_id,
            PlanRow.version == version,
            PlanRow.status == PlanStatus.DRAFT.value,
        )
        .values(version=PlanRow.version + 1, updated_at=func.now())
        .returning(PlanRow)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one_or_none()


async def mark_ready(session: AsyncSession, workspace_id: UUID, plan_id: UUID) -> PlanRow | None:
    """Make a draft plan ``ready``; ``None`` when it is not a draft (so no event twice)."""
    stmt = (
        update(PlanRow)
        .where(
            PlanRow.workspace_id == workspace_id,
            PlanRow.id == plan_id,
            PlanRow.status == PlanStatus.DRAFT.value,
        )
        .values(
            status=PlanStatus.READY.value,
            ready_at=func.now(),
            version=PlanRow.version + 1,
            updated_at=func.now(),
        )
        .returning(PlanRow)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one_or_none()
