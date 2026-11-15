"""Postgres access for ``identity.members``. Queries only; no business rules."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.modules.identity.dto import MemberRole
from metis.modules.identity.models import MemberRow, WorkspaceRow


async def get_role(session: AsyncSession, workspace_id: UUID, user_id: UUID) -> MemberRole | None:
    stmt = select(MemberRow.role).where(
        MemberRow.workspace_id == workspace_id, MemberRow.user_id == user_id
    )
    role = (await session.scalars(stmt)).one_or_none()
    return MemberRole(role) if role is not None else None


async def create(
    session: AsyncSession, workspace_id: UUID, user_id: UUID, role: MemberRole
) -> bool:
    """Insert a membership; ``False`` if the user is already a member."""
    stmt = (
        insert(MemberRow)
        .values(workspace_id=workspace_id, user_id=user_id, role=role.value)
        .on_conflict_do_nothing(index_elements=[MemberRow.workspace_id, MemberRow.user_id])
        .returning(MemberRow.user_id)
    )
    return (await session.scalars(stmt)).one_or_none() is not None


async def list_for_user(
    session: AsyncSession, user_id: UUID
) -> list[tuple[WorkspaceRow, MemberRole]]:
    stmt = (
        select(WorkspaceRow, MemberRow.role)
        .join(MemberRow, MemberRow.workspace_id == WorkspaceRow.id)
        .where(MemberRow.user_id == user_id)
        .order_by(WorkspaceRow.created_at, WorkspaceRow.id)
    )
    return [(ws, MemberRole(role)) for ws, role in (await session.execute(stmt)).all()]
