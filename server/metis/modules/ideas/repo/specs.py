"""Postgres access for ``ideas.spec_versions``. Queries only; no business rules.

Every query filters by ``workspace_id`` as well as relying on RLS. Versions are numbered per
idea; nothing here updates or deletes one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from metis.helpers.ids import uuid7
from metis.modules.ideas.dto.spec import SpecSource
from metis.modules.ideas.models import SpecVersionRow

if TYPE_CHECKING:
    from uuid import UUID


async def lock_idea(session: AsyncSession, idea_id: UUID) -> None:
    """Serialize writers of one idea's versions until the transaction ends (advisory lock)."""
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(str(idea_id), 1)))
    )


async def latest(session: AsyncSession, workspace_id: UUID, idea_id: UUID) -> SpecVersionRow | None:
    stmt = (
        select(SpecVersionRow)
        .where(SpecVersionRow.workspace_id == workspace_id, SpecVersionRow.idea_id == idea_id)
        .order_by(SpecVersionRow.number.desc())
        .limit(1)
    )
    return (await session.scalars(stmt.execution_options(populate_existing=True))).first()


async def get_by_number(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, number: int
) -> SpecVersionRow | None:
    stmt = select(SpecVersionRow).where(
        SpecVersionRow.workspace_id == workspace_id,
        SpecVersionRow.idea_id == idea_id,
        SpecVersionRow.number == number,
    )
    return (await session.scalars(stmt)).first()


async def get(session: AsyncSession, workspace_id: UUID, version_id: UUID) -> SpecVersionRow | None:
    stmt = select(SpecVersionRow).where(
        SpecVersionRow.workspace_id == workspace_id, SpecVersionRow.id == version_id
    )
    return (await session.scalars(stmt)).first()


async def get_agent_draft(
    session: AsyncSession, workspace_id: UUID, run_id: UUID
) -> SpecVersionRow | None:
    """The version the Architect drafted in this run, if any (the unique index allows one)."""
    stmt = select(SpecVersionRow).where(
        SpecVersionRow.workspace_id == workspace_id,
        SpecVersionRow.run_id == run_id,
        SpecVersionRow.source == SpecSource.AGENT.value,
    )
    return (await session.scalars(stmt)).first()


async def list_for_idea(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID
) -> list[SpecVersionRow]:
    """The idea's versions, newest first."""
    stmt = (
        select(SpecVersionRow)
        .where(SpecVersionRow.workspace_id == workspace_id, SpecVersionRow.idea_id == idea_id)
        .order_by(SpecVersionRow.number.desc())
    )
    return list(await session.scalars(stmt))


async def create(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    *,
    number: int,
    source: str,
    content_md: str,
    sections: dict[str, Any],
    run_id: UUID | None,
    created_by: UUID | None,
) -> SpecVersionRow:
    row = SpecVersionRow(
        id=uuid7(),
        workspace_id=workspace_id,
        idea_id=idea_id,
        number=number,
        source=source,
        content_md=content_md,
        sections=sections,
        run_id=run_id,
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    return row
