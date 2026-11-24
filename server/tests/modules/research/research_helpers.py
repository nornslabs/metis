"""Setup helpers for the research tests: a run to research, sessions as ``metis_app``, inputs."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.core.db import set_workspace
from metis.helpers.validation import validate_input
from metis.modules.research import EMBEDDING_DIMENSIONS, NewCompetitor, NewResearchItem
from tests.agent.llm_helpers import make_run, workspace_without_key

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from uuid import UUID


@dataclass(frozen=True)
class Run:
    workspace_id: UUID
    idea_id: UUID
    run_id: UUID


async def new_run(engine: AsyncEngine, sub: str = "ada") -> Run:
    """A queued run of a fresh idea in a new user's personal workspace."""
    workspace_id = await workspace_without_key(engine, sub)
    return await another_run(engine, workspace_id)


async def another_run(engine: AsyncEngine, workspace_id: UUID) -> Run:
    """A queued run of a new idea in ``workspace_id``."""
    run_id = await make_run(engine, workspace_id)
    async with engine.connect() as conn:
        idea_id = await conn.scalar(
            text("SELECT idea_id FROM ideas.workflow_runs WHERE id = :id"), {"id": run_id}
        )
    return Run(workspace_id, idea_id, run_id)


async def archive(engine: AsyncEngine, idea_id: UUID) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE ideas.ideas SET archived_at = now() WHERE id = :id"), {"id": idea_id}
        )


@asynccontextmanager
async def in_workspace(
    sessions: async_sessionmaker[AsyncSession], workspace_id: UUID
) -> AsyncGenerator[AsyncSession]:
    """One committed transaction as ``metis_app``, scoped to ``workspace_id``."""
    async with sessions() as session, session.begin():
        await set_workspace(session, workspace_id)
        yield session


def item(**fields: Any) -> NewResearchItem:
    data: dict[str, Any] = {
        "kind": "market_fact",
        "title": "Freelancers use spreadsheets",
        "url": "https://example.com/report",
        "claim": "Most freelancers track clients in spreadsheets.",
        "quote": "62% of freelancers use spreadsheets.",
        "confidence": 0.8,
    }
    data.update(fields)
    return validate_input(NewResearchItem, **data)


def competitor(**fields: Any) -> NewCompetitor:
    data: dict[str, Any] = {"name": "Acme CRM", "url": "https://www.acme.com/pricing"}
    data.update(fields)
    return validate_input(NewCompetitor, **data)


def vector(*head: float) -> list[float]:
    """A 1536-dimension vector starting with ``head``, zeros after."""
    return [*head, *([0.0] * (EMBEDDING_DIMENSIONS - len(head)))]
