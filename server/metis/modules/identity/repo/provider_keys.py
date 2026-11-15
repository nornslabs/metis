"""Postgres access for ``identity.provider_keys``. Queries only; no business rules."""

from __future__ import annotations

from base64 import b64decode, b64encode
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.crypto import SealedSecret
from metis.core.errors import SecretDecryptError
from metis.helpers.ids import uuid7
from metis.modules.identity.dto import ProviderKind
from metis.modules.identity.models import ProviderKeyRow

_SEALED_BYTES_FIELDS = ("ciphertext", "nonce", "wrapped_key")
_UNREADABLE_SECRET = "A stored secret could not be read. Please re-enter it."


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
