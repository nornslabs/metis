"""Postgres access for ``research.items``. Queries only; no business rules.

Every query filters by ``workspace_id`` as well as relying on RLS. Items are ordered by
their uuid7 ``id``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.helpers.ids import uuid7
from metis.modules.research.models import ItemRow


async def create(
    session: AsyncSession,
    workspace_id: UUID,
    snapshot_id: UUID,
    *,
    kind: str,
    title: str,
    url: str | None,
    published_at: date | None,
    quote: str | None,
    claim: str,
    confidence: float,
) -> ItemRow:
    stmt = (
        insert(ItemRow)
        .values(
            id=uuid7(),
            workspace_id=workspace_id,
            snapshot_id=snapshot_id,
            kind=kind,
            title=title,
            url=url,
            published_at=published_at,
            quote=quote,
            claim=claim,
            confidence=Decimal(str(confidence)),
        )
        .returning(ItemRow)
    )
    return (await session.scalars(stmt)).one()


async def list_for_snapshot(
    session: AsyncSession, workspace_id: UUID, snapshot_id: UUID
) -> list[ItemRow]:
    stmt = (
        select(ItemRow)
        .where(ItemRow.workspace_id == workspace_id, ItemRow.snapshot_id == snapshot_id)
        .order_by(ItemRow.id)
    )
    return list(await session.scalars(stmt))
