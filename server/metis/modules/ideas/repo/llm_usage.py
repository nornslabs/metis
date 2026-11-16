"""Postgres access for ``ideas.llm_usage``. Queries only; no business rules."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from metis.modules.ideas.dto import NewLlmUsage
from metis.modules.ideas.models import LlmUsageRow


async def create(session: AsyncSession, workspace_id: UUID, usage: NewLlmUsage) -> LlmUsageRow:
    row = LlmUsageRow(
        workspace_id=workspace_id,
        run_id=usage.run_id,
        model=usage.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_usd=usage.cost_usd,
    )
    session.add(row)
    await session.flush()
    return row


async def list_for_run(
    session: AsyncSession, workspace_id: UUID, run_id: UUID
) -> list[LlmUsageRow]:
    stmt = (
        select(LlmUsageRow)
        .where(LlmUsageRow.workspace_id == workspace_id, LlmUsageRow.run_id == run_id)
        .order_by(LlmUsageRow.created_at, LlmUsageRow.id)
    )
    return list((await session.scalars(stmt)).all())
