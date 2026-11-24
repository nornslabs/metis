"""Postgres access for ``identity.workspace_settings``. Queries only; no business rules."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.modules.identity.dto import DEFAULT_MAX_STEPS, DEFAULT_RUN_BUDGET_USD
from metis.modules.identity.models import WorkspaceSettingsRow


async def get(session: AsyncSession, workspace_id: UUID) -> WorkspaceSettingsRow | None:
    return await session.get(WorkspaceSettingsRow, workspace_id)


async def create(
    session: AsyncSession,
    workspace_id: UUID,
    *,
    run_budget_usd: Decimal,
    max_steps: int,
) -> WorkspaceSettingsRow | None:
    """Create the settings row at version 1; ``None`` if one already exists."""
    stmt = (
        insert(WorkspaceSettingsRow)
        .values(
            workspace_id=workspace_id,
            run_budget_usd=run_budget_usd,
            max_steps=max_steps,
        )
        .on_conflict_do_nothing(index_elements=[WorkspaceSettingsRow.workspace_id])
        .returning(WorkspaceSettingsRow)
    )
    return (await session.scalars(stmt)).one_or_none()


async def update_at_version(
    session: AsyncSession, workspace_id: UUID, *, version: int, changes: dict[str, object]
) -> WorkspaceSettingsRow | None:
    """Apply ``changes`` if the row is still at ``version``; ``None`` on a mismatch."""
    stmt = (
        update(WorkspaceSettingsRow)
        .where(
            WorkspaceSettingsRow.workspace_id == workspace_id,
            WorkspaceSettingsRow.version == version,
        )
        .values(**changes, version=WorkspaceSettingsRow.version + 1, updated_at=func.now())
        .returning(WorkspaceSettingsRow)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one_or_none()


async def set_linear_team(session: AsyncSession, workspace_id: UUID, team_id: str) -> None:
    """Save the Linear team; creates the row from the defaults when none exists. The version
    is not bumped: a team picked by a run must not make an owner's open settings form stale."""
    stmt = (
        insert(WorkspaceSettingsRow)
        .values(
            workspace_id=workspace_id,
            run_budget_usd=DEFAULT_RUN_BUDGET_USD,
            max_steps=DEFAULT_MAX_STEPS,
            linear_team_id=team_id,
        )
        .on_conflict_do_update(
            index_elements=[WorkspaceSettingsRow.workspace_id],
            set_={"linear_team_id": team_id, "updated_at": func.now()},
        )
    )
    await session.execute(stmt)
