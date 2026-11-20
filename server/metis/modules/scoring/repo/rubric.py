"""Postgres access for ``scoring.rubric_versions``. Queries only; the table is global."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from metis.modules.scoring.models import RubricVersionRow


async def latest(session: AsyncSession) -> RubricVersionRow | None:
    stmt = select(RubricVersionRow).order_by(RubricVersionRow.id.desc()).limit(1)
    return (await session.scalars(stmt)).one_or_none()


async def get(session: AsyncSession, version: int) -> RubricVersionRow | None:
    return await session.get(RubricVersionRow, version)
