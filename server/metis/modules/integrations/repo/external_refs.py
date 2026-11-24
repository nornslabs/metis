"""Postgres access for ``integrations.external_refs``. Queries only; no business rules."""

from __future__ import annotations

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from metis.modules.integrations.models import ExternalRefRow


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
