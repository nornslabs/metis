"""Postgres access for ``identity.workspaces``. Queries only; no business rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.helpers.ids import uuid7
from metis.modules.identity.models import WorkspaceRow

if TYPE_CHECKING:
    from uuid import UUID


async def create(
    session: AsyncSession, name: str, created_by: UUID, *, is_personal: bool
) -> WorkspaceRow | None:
    """Insert a workspace; ``None`` if it is personal and the user already has one."""
    stmt = insert(WorkspaceRow).values(
        id=uuid7(), name=name, is_personal=is_personal, created_by=created_by
    )
    if is_personal:
        stmt = stmt.on_conflict_do_nothing(
            index_elements=[WorkspaceRow.created_by], index_where=text("is_personal")
        )
    return (await session.scalars(stmt.returning(WorkspaceRow))).one_or_none()


async def get_personal(session: AsyncSession, user_id: UUID) -> WorkspaceRow:
    stmt = select(WorkspaceRow).where(
        WorkspaceRow.created_by == user_id, WorkspaceRow.is_personal.is_(True)
    )
    return (await session.scalars(stmt)).one()


async def get(session: AsyncSession, workspace_id: UUID) -> WorkspaceRow | None:
    return await session.get(WorkspaceRow, workspace_id)
