"""LLM usage: one row per completed call, so spend is visible and budgets can be enforced later.

Like every service function it takes the caller's ``AsyncSession`` and never commits.
The caller scopes the session to the workspace (``set_workspace``) and decides the
transaction, so a failed run keeps the usage it already recorded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.logging import get_logger
from metis.modules.ideas import repo
from metis.modules.ideas.dto import NewLlmUsage

if TYPE_CHECKING:
    from uuid import UUID

logger = get_logger(__name__)


async def record_llm_usage(session: AsyncSession, workspace_id: UUID, usage: NewLlmUsage) -> None:
    """Save the tokens and cost of one completed LLM call."""
    await repo.llm_usage.create(session, workspace_id, usage)
    logger.info(
        "llm.usage_recorded",
        run_id=str(usage.run_id),
        model=usage.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )
