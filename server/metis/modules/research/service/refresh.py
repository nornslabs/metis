"""Manual score refresh orchestration over the research and ideas module surfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import ResearchNotFoundError
from metis.modules import ideas
from metis.modules.ideas import RunKind, WorkflowRun
from metis.modules.research.service import snapshots

if TYPE_CHECKING:
    from uuid import UUID


async def start_rescore(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    idempotency_key: str,
) -> WorkflowRun:
    """Queue a rescore only when the idea has a closed snapshot to score."""
    if await snapshots.latest_snapshot(session, workspace_id, idea_id) is None:
        raise ResearchNotFoundError(
            "No completed market research exists for this idea. "
            "Use Re-check market to collect evidence before rescoring."
        )
    return await ideas.start_refresh_run(
        session, workspace_id, idea_id, idempotency_key, RunKind.RESCORE
    )


async def start_market_recheck(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    idempotency_key: str,
) -> WorkflowRun:
    """Queue a fresh market scan followed by scoring."""
    return await ideas.start_refresh_run(
        session, workspace_id, idea_id, idempotency_key, RunKind.MARKET_RECHECK
    )
