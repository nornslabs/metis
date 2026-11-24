"""Postgres access for ``identity.provider_keys``. Queries only; no business rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.crypto import SealedSecret, seal_to_json
from metis.helpers.ids import uuid7
from metis.modules.identity.dto import ProviderKind
from metis.modules.identity.models import ProviderKeyRow

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID


async def upsert(
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


async def get(
    session: AsyncSession, workspace_id: UUID, kind: ProviderKind
) -> ProviderKeyRow | None:
    stmt = select(ProviderKeyRow).where(
        ProviderKeyRow.workspace_id == workspace_id, ProviderKeyRow.kind == kind.value
    )
    return (await session.scalars(stmt)).one_or_none()


async def list_for_workspace(session: AsyncSession, workspace_id: UUID) -> list[ProviderKeyRow]:
    stmt = select(ProviderKeyRow).where(ProviderKeyRow.workspace_id == workspace_id)
    return list((await session.scalars(stmt)).all())


async def remove(session: AsyncSession, workspace_id: UUID, kind: ProviderKind) -> bool:
    """Delete the key; ``False`` if there was none."""
    stmt = (
        delete(ProviderKeyRow)
        .where(ProviderKeyRow.workspace_id == workspace_id, ProviderKeyRow.kind == kind.value)
        .returning(ProviderKeyRow.id)
    )
    return (await session.scalars(stmt)).one_or_none() is not None


async def record_test(
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
