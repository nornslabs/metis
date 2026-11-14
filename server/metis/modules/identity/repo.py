"""Data access for the ``identity`` schema. Queries only; no business rules."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import MetisError
from metis.core.ids import uuid7
from metis.modules.identity.models import MemberRow, UserRow, WorkspaceRow
from metis.modules.identity.schemas import MemberRole, UserClaims

USER_SETTING = "app.user_id"
WORKSPACE_SETTING = "app.workspace_id"


async def _set_config(session: AsyncSession, setting: str, value: str) -> None:
    await session.execute(
        text("SELECT set_config(:setting, :value, true)"), {"setting": setting, "value": value}
    )


@asynccontextmanager
async def rls_context(session: AsyncSession, setting: str, value: UUID) -> AsyncIterator[None]:
    """Set an RLS setting for the block, then restore the caller's value.

    The setting is transaction-local. It is restored after success and after a
    domain error (the transaction is still usable); after a database error the
    transaction is aborted, so there is nothing left to restore.
    """
    previous = await session.scalar(
        text("SELECT current_setting(:setting, true)"), {"setting": setting}
    )
    await _set_config(session, setting, str(value))
    try:
        yield
    except MetisError:
        await _set_config(session, setting, previous or "")
        raise
    await _set_config(session, setting, previous or "")


async def upsert_user(session: AsyncSession, claims: UserClaims) -> UserRow | None:
    """Insert or update the user keyed on ``auth_sub``.

    Returns ``None`` when the email already belongs to another account (the only
    other unique constraint); a savepoint keeps the caller's transaction usable.
    """
    stmt = (
        insert(UserRow)
        .values(
            id=uuid7(),
            auth_sub=claims.sub,
            email=claims.email,
            name=claims.name,
            image=claims.image,
        )
        .on_conflict_do_update(
            index_elements=[UserRow.auth_sub],
            set_={"email": claims.email, "name": claims.name, "image": claims.image},
        )
        .returning(UserRow)
    )
    try:
        async with session.begin_nested():
            return (await session.scalars(stmt)).one()
    except IntegrityError:
        return None


async def insert_workspace(
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


async def get_personal_workspace(session: AsyncSession, user_id: UUID) -> WorkspaceRow:
    stmt = select(WorkspaceRow).where(
        WorkspaceRow.created_by == user_id, WorkspaceRow.is_personal.is_(True)
    )
    return (await session.scalars(stmt)).one()


async def get_user_by_email(session: AsyncSession, email: str) -> UserRow | None:
    return (await session.scalars(select(UserRow).where(UserRow.email == email))).one_or_none()


async def get_workspace(session: AsyncSession, workspace_id: UUID) -> WorkspaceRow | None:
    return await session.get(WorkspaceRow, workspace_id)


async def get_member_role(
    session: AsyncSession, workspace_id: UUID, user_id: UUID
) -> MemberRole | None:
    stmt = select(MemberRow.role).where(
        MemberRow.workspace_id == workspace_id, MemberRow.user_id == user_id
    )
    role = (await session.scalars(stmt)).one_or_none()
    return MemberRole(role) if role is not None else None


async def insert_member(
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


async def list_memberships(
    session: AsyncSession, user_id: UUID
) -> list[tuple[WorkspaceRow, MemberRole]]:
    stmt = (
        select(WorkspaceRow, MemberRow.role)
        .join(MemberRow, MemberRow.workspace_id == WorkspaceRow.id)
        .where(MemberRow.user_id == user_id)
        .order_by(WorkspaceRow.created_at, WorkspaceRow.id)
    )
    return [(ws, MemberRole(role)) for ws, role in (await session.execute(stmt)).all()]
