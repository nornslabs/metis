"""Data access for the ``identity`` schema. Queries only; no business rules."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.ids import uuid7
from metis.modules.identity.models import MemberRow, UserRow, WorkspaceRow

PERSONAL_WORKSPACE_NAME = "Personal"


async def set_user_context(session: AsyncSession, user_id: UUID) -> None:
    """Scope RLS reads of ``members`` to this user's rows, for this transaction."""
    await session.execute(text("SELECT set_config('app.user_id', :v, true)"), {"v": str(user_id)})


async def set_workspace_context(session: AsyncSession, workspace_id: UUID) -> None:
    """Scope RLS on tenant tables to this workspace, for this transaction."""
    await session.execute(
        text("SELECT set_config('app.workspace_id', :v, true)"), {"v": str(workspace_id)}
    )


async def upsert_user(
    session: AsyncSession, auth_sub: str, email: str, name: str | None, image: str | None
) -> UserRow:
    stmt = (
        insert(UserRow)
        .values(id=uuid7(), auth_sub=auth_sub, email=email, name=name, image=image)
        .on_conflict_do_update(
            index_elements=[UserRow.auth_sub],
            set_={"email": email, "name": name, "image": image},
        )
        .returning(UserRow)
    )
    return (await session.scalars(stmt)).one()


async def insert_personal_workspace(session: AsyncSession, user_id: UUID) -> UUID | None:
    """Insert the user's personal workspace; ``None`` if it already exists."""
    stmt = (
        insert(WorkspaceRow)
        .values(id=uuid7(), name=PERSONAL_WORKSPACE_NAME, is_personal=True, created_by=user_id)
        .on_conflict_do_nothing(
            index_elements=[WorkspaceRow.created_by], index_where=text("is_personal")
        )
        .returning(WorkspaceRow.id)
    )
    return (await session.scalars(stmt)).one_or_none()


async def insert_workspace(session: AsyncSession, name: str, user_id: UUID) -> WorkspaceRow:
    stmt = (
        insert(WorkspaceRow)
        .values(id=uuid7(), name=name, is_personal=False, created_by=user_id)
        .returning(WorkspaceRow)
    )
    return (await session.scalars(stmt)).one()


async def get_personal_workspace(session: AsyncSession, user_id: UUID) -> WorkspaceRow:
    stmt = select(WorkspaceRow).where(
        WorkspaceRow.created_by == user_id, WorkspaceRow.is_personal.is_(True)
    )
    return (await session.scalars(stmt)).one()


async def get_user_by_email(session: AsyncSession, email: str) -> UserRow | None:
    return (await session.scalars(select(UserRow).where(UserRow.email == email))).one_or_none()


async def get_workspace(session: AsyncSession, workspace_id: UUID) -> WorkspaceRow | None:
    return await session.get(WorkspaceRow, workspace_id)


async def get_member_role(session: AsyncSession, workspace_id: UUID, user_id: UUID) -> str | None:
    stmt = select(MemberRow.role).where(
        MemberRow.workspace_id == workspace_id, MemberRow.user_id == user_id
    )
    return (await session.scalars(stmt)).one_or_none()


async def insert_member(
    session: AsyncSession, workspace_id: UUID, user_id: UUID, role: str
) -> bool:
    """Insert a membership; ``False`` if the user is already a member."""
    stmt = (
        insert(MemberRow)
        .values(workspace_id=workspace_id, user_id=user_id, role=role)
        .on_conflict_do_nothing(index_elements=[MemberRow.workspace_id, MemberRow.user_id])
        .returning(MemberRow.user_id)
    )
    return (await session.scalars(stmt)).one_or_none() is not None


async def list_memberships(session: AsyncSession, user_id: UUID) -> list[tuple[WorkspaceRow, str]]:
    stmt = (
        select(WorkspaceRow, MemberRow.role)
        .join(MemberRow, MemberRow.workspace_id == WorkspaceRow.id)
        .where(MemberRow.user_id == user_id)
        .order_by(WorkspaceRow.created_at, WorkspaceRow.id)
    )
    return [(ws, role) for ws, role in (await session.execute(stmt)).all()]
