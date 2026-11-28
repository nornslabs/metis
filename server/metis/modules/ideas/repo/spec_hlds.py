"""Postgres access for ``ideas.spec_hlds``. Queries only; no business rules.

Every query filters by ``workspace_id`` as well as relying on RLS. Nothing here updates or
deletes a row.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from metis.helpers.ids import uuid7
from metis.modules.ideas.models import SpecHldRow


async def latest(session: AsyncSession, workspace_id: UUID, idea_id: UUID) -> SpecHldRow | None:
    """The HLD written for the newest spec version that has one."""
    stmt = (
        select(SpecHldRow)
        .where(SpecHldRow.workspace_id == workspace_id, SpecHldRow.idea_id == idea_id)
        .order_by(SpecHldRow.spec_version_number.desc())
        .limit(1)
    )
    return (await session.scalars(stmt.execution_options(populate_existing=True))).first()


async def get_by_number(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, spec_version_number: int
) -> SpecHldRow | None:
    stmt = select(SpecHldRow).where(
        SpecHldRow.workspace_id == workspace_id,
        SpecHldRow.idea_id == idea_id,
        SpecHldRow.spec_version_number == spec_version_number,
    )
    return (await session.scalars(stmt)).first()


async def create(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    *,
    spec_version_number: int,
    spec_hash: str,
    build_language: str,
    content_md: str,
) -> SpecHldRow:
    row = SpecHldRow(
        id=uuid7(),
        workspace_id=workspace_id,
        idea_id=idea_id,
        spec_version_number=spec_version_number,
        spec_hash=spec_hash,
        build_language=build_language,
        content_md=content_md,
    )
    session.add(row)
    await session.flush()
    return row
