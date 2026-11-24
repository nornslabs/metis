"""Postgres access for ``integrations.external_refs``. Queries only; no business rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.helpers.ids import uuid7
from metis.modules.integrations.models import ExternalRefRow

if TYPE_CHECKING:
    from collections.abc import Collection
    from uuid import UUID


async def list_for(
    session: AsyncSession,
    workspace_id: UUID,
    provider: str,
    local_kind: str,
    local_ids: Collection[UUID],
) -> list[ExternalRefRow]:
    """The refs of ``local_kind`` records among ``local_ids``."""
    if not local_ids:
        return []
    rows = await session.scalars(
        select(ExternalRefRow).where(
            ExternalRefRow.workspace_id == workspace_id,
            ExternalRefRow.provider == provider,
            ExternalRefRow.local_kind == local_kind,
            ExternalRefRow.local_id.in_(local_ids),
        )
    )
    return list(rows)


async def upsert(
    session: AsyncSession,
    workspace_id: UUID,
    provider: str,
    local_kind: str,
    local_id: UUID,
    external_id: str,
    external_url: str | None,
) -> ExternalRefRow:
    """Insert the ref, or update the Linear id and url of the existing row for the same
    ``(workspace, provider, local_kind, local_id)``; never a second row."""
    base = insert(ExternalRefRow).values(
        id=uuid7(),
        workspace_id=workspace_id,
        provider=provider,
        local_kind=local_kind,
        local_id=local_id,
        external_id=external_id,
        external_url=external_url,
    )
    stmt = base.on_conflict_do_update(
        constraint="uq_external_refs_local",
        set_={"external_id": base.excluded.external_id, "external_url": base.excluded.external_url},
    ).returning(ExternalRefRow)
    return (await session.scalars(stmt)).one()
