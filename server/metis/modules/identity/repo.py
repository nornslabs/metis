"""Data access for the ``identity`` schema. Queries only; no business rules."""

from __future__ import annotations

from base64 import b64decode, b64encode
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.crypto import SealedSecret
from metis.core.db import set_setting
from metis.core.errors import MetisError, SecretDecryptError
from metis.helpers.ids import uuid7
from metis.modules.identity.models import (
    MemberRow,
    ProviderKeyRow,
    UserRow,
    WorkspaceRow,
    WorkspaceSettingsRow,
)
from metis.modules.identity.schemas import MemberRole, ProviderKind, UserClaims

_SEALED_BYTES_FIELDS = ("ciphertext", "nonce", "wrapped_key")
_UNREADABLE_SECRET = "A stored secret could not be read. Please re-enter it."


@asynccontextmanager
async def rls_context(session: AsyncSession, setting: str, value: UUID) -> AsyncGenerator[None]:
    """Set an RLS setting for the block, then restore the caller's value.

    The setting is transaction-local. It is restored after success and after a
    domain error (the transaction is still usable); after a database error the
    transaction is aborted, so there is nothing left to restore.
    """
    previous = await session.scalar(
        text("SELECT current_setting(:setting, true)"), {"setting": setting}
    )
    await set_setting(session, setting, str(value))
    try:
        yield
    except MetisError:
        await set_setting(session, setting, previous or "")
        raise
    await set_setting(session, setting, previous or "")


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


# ------------------------------------------------------------- provider keys
def seal_to_json(sealed: SealedSecret) -> dict[str, Any]:
    """Storage form of a sealed secret: byte fields as base64 text."""
    stored: dict[str, Any] = {
        name: b64encode(getattr(sealed, name)).decode() for name in _SEALED_BYTES_FIELDS
    }
    return {**stored, "key_version": sealed.key_version}


def seal_from_json(stored: dict[str, Any]) -> SealedSecret:
    """Inverse of ``seal_to_json``; a malformed row fails like a tampered one."""
    try:
        fields = {name: b64decode(stored[name]) for name in _SEALED_BYTES_FIELDS}
        return SealedSecret(**fields, key_version=int(stored["key_version"]))
    except (KeyError, TypeError, ValueError):
        raise SecretDecryptError(_UNREADABLE_SECRET) from None


async def upsert_provider_key(
    session: AsyncSession,
    workspace_id: UUID,
    kind: ProviderKind,
    *,
    base_url: str | None,
    model: str | None,
    sealed: SealedSecret,
    masked: str,
) -> ProviderKeyRow:
    """Insert or replace the workspace's key of ``kind``; a replace bumps ``version``
    and clears the last test result."""
    values = {
        "base_url": base_url,
        "model": model,
        "sealed": seal_to_json(sealed),
        "masked": masked,
    }
    stmt = (
        insert(ProviderKeyRow)
        .values(id=uuid7(), workspace_id=workspace_id, kind=kind.value, **values)
        .on_conflict_do_update(
            index_elements=[ProviderKeyRow.workspace_id, ProviderKeyRow.kind],
            set_={
                **values,
                "last_tested_at": None,
                "last_test_ok": None,
                "version": ProviderKeyRow.version + 1,
                "updated_at": func.now(),
            },
        )
        .returning(ProviderKeyRow)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one()


async def get_provider_key(
    session: AsyncSession, workspace_id: UUID, kind: ProviderKind
) -> ProviderKeyRow | None:
    stmt = select(ProviderKeyRow).where(
        ProviderKeyRow.workspace_id == workspace_id, ProviderKeyRow.kind == kind.value
    )
    return (await session.scalars(stmt)).one_or_none()


async def list_provider_keys(session: AsyncSession, workspace_id: UUID) -> list[ProviderKeyRow]:
    stmt = select(ProviderKeyRow).where(ProviderKeyRow.workspace_id == workspace_id)
    return list((await session.scalars(stmt)).all())


async def delete_provider_key(
    session: AsyncSession, workspace_id: UUID, kind: ProviderKind
) -> bool:
    """Delete the key; ``False`` if there was none."""
    stmt = (
        delete(ProviderKeyRow)
        .where(ProviderKeyRow.workspace_id == workspace_id, ProviderKeyRow.kind == kind.value)
        .returning(ProviderKeyRow.id)
    )
    return (await session.scalars(stmt)).one_or_none() is not None


async def record_key_test(
    session: AsyncSession, key_id: UUID, *, ok: bool, tested_at: datetime
) -> ProviderKeyRow:
    stmt = (
        update(ProviderKeyRow)
        .where(ProviderKeyRow.id == key_id)
        .values(last_tested_at=tested_at, last_test_ok=ok)
        .returning(ProviderKeyRow)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one()


# ---------------------------------------------------------- workspace settings
async def get_workspace_settings(
    session: AsyncSession, workspace_id: UUID
) -> WorkspaceSettingsRow | None:
    return await session.get(WorkspaceSettingsRow, workspace_id)


async def insert_workspace_settings(
    session: AsyncSession, workspace_id: UUID, *, run_budget_usd: Decimal, max_steps: int
) -> WorkspaceSettingsRow | None:
    """Create the settings row at version 1; ``None`` if one already exists."""
    stmt = (
        insert(WorkspaceSettingsRow)
        .values(workspace_id=workspace_id, run_budget_usd=run_budget_usd, max_steps=max_steps)
        .on_conflict_do_nothing(index_elements=[WorkspaceSettingsRow.workspace_id])
        .returning(WorkspaceSettingsRow)
    )
    return (await session.scalars(stmt)).one_or_none()


async def update_workspace_settings(
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
