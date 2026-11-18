"""Postgres access for ``research.competitors``. Queries only; no business rules.

Every query filters by ``workspace_id`` as well as relying on RLS.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.helpers.ids import uuid7
from metis.modules.research.models import CompetitorRow

_LIKE_ESCAPE = "\\"


async def upsert(
    session: AsyncSession,
    workspace_id: UUID,
    *,
    name: str,
    url: str,
    domain: str,
    description: str | None,
    pricing: str | None,
    embedding: Sequence[float] | None,
) -> CompetitorRow:
    """Insert, or refresh the row with the same ``(workspace_id, domain)``.

    A refresh takes the new name and URL, keeps the stored description, pricing and
    embedding where the new ones are ``None``, and bumps ``updated_at``.
    """
    values = insert(CompetitorRow).values(
        id=uuid7(),
        workspace_id=workspace_id,
        name=name,
        url=url,
        domain=domain,
        description=description,
        pricing=pricing,
        embedding=list(embedding) if embedding is not None else None,
    )
    new = values.excluded
    stmt = values.on_conflict_do_update(
        index_elements=[CompetitorRow.workspace_id, CompetitorRow.domain],
        set_={
            "name": new.name,
            "url": new.url,
            "description": func.coalesce(new.description, CompetitorRow.description),
            "pricing": func.coalesce(new.pricing, CompetitorRow.pricing),
            "embedding": func.coalesce(new.embedding, CompetitorRow.embedding),
            "updated_at": func.now(),
        },
    ).returning(CompetitorRow)
    row: CompetitorRow = (
        await session.scalars(stmt.execution_options(populate_existing=True))
    ).one()
    return row


async def get(
    session: AsyncSession, workspace_id: UUID, competitor_id: UUID
) -> CompetitorRow | None:
    stmt = select(CompetitorRow).where(
        CompetitorRow.workspace_id == workspace_id, CompetitorRow.id == competitor_id
    )
    return (await session.scalars(stmt)).one_or_none()


async def nearest(
    session: AsyncSession, workspace_id: UUID, embedding: Sequence[float], limit: int
) -> list[tuple[CompetitorRow, float]]:
    """Competitors with an embedding, closest first, with their cosine distance."""
    distance = CompetitorRow.embedding.cosine_distance(list(embedding))
    stmt = (
        select(CompetitorRow, distance)
        .where(CompetitorRow.workspace_id == workspace_id, CompetitorRow.embedding.is_not(None))
        .order_by(distance, CompetitorRow.id)
        .limit(limit)
    )
    return [(row, float(dist)) for row, dist in (await session.execute(stmt)).all()]


async def matching_name(
    session: AsyncSession, workspace_id: UUID, text: str, limit: int
) -> list[CompetitorRow]:
    """Competitors whose name or domain contains ``text`` (case-insensitive), by name."""
    pattern = f"%{_escape_like(text.lower())}%"
    stmt = (
        select(CompetitorRow)
        .where(
            CompetitorRow.workspace_id == workspace_id,
            or_(
                func.lower(CompetitorRow.name).like(pattern, escape=_LIKE_ESCAPE),
                CompetitorRow.domain.like(pattern, escape=_LIKE_ESCAPE),
            ),
        )
        .order_by(func.lower(CompetitorRow.name), CompetitorRow.id)
        .limit(limit)
    )
    return list(await session.scalars(stmt))


def _escape_like(text: str) -> str:
    for char in (_LIKE_ESCAPE, "%", "_"):
        text = text.replace(char, f"{_LIKE_ESCAPE}{char}")
    return text
