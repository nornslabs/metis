"""Helpers for the spec tests: an idea at ``spec_draft`` with an agent draft, and readers of what
the database holds (the outbox, the confirmed version)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.helpers.ids import uuid7
from metis.modules import ideas
from metis.modules.ideas import NewSpecVersion, SpecSource
from metis.modules.ideas.helpers.spec_markdown import render_markdown
from tests.modules.ideas.idea_helpers import Caller, create
from tests.modules.scoring.scoring_helpers import in_workspace

SECTIONS = {
    "problem": "Freelancers lose track of leads.",
    "target_users": "Solo freelancers.",
    "solution": "A tiny CRM.",
    "key_features": "- MVP: a lead list\n- Later: reminders",
    "non_goals": "Team features.",
    "competitive_edge": "Simple and cheap.",
    "success_metrics": "50 weekly active users.",
    "risks": "Crowded market.",
    "open_questions": "None.",
}
DRAFT = render_markdown(SECTIONS)
SPEC_REVIEW = {"type": "spec_review", "spec_version_id": str(uuid4()), "number": 1, "kind": None}


async def set_stage(engine: AsyncEngine, idea_id: str, stage: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE ideas.ideas SET stage = :stage WHERE id = :id"),
            {"stage": stage, "id": idea_id},
        )


async def draft_idea(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    caller: Caller,
    *,
    stage: str = "spec_draft",
) -> dict[str, Any]:
    """A new idea at ``stage`` with the Architect's version 1 saved."""
    idea = await create(client, caller)
    await set_stage(engine, idea["id"], stage)
    workspace_id = UUID(caller.workspace_id)
    async with in_workspace(sessions, workspace_id) as session:
        await ideas.save_spec_version(
            session,
            workspace_id,
            UUID(idea["id"]),
            NewSpecVersion(content_md=DRAFT, source=SpecSource.AGENT),
        )
    return idea


async def waiting_run(engine: AsyncEngine, caller: Caller, idea_id: str) -> str:
    """A run of the idea paused on ``spec_review``."""
    run_id = str(uuid7())
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ideas.workflow_runs "
                "(id, workspace_id, idea_id, status, pending_interrupt) "
                "VALUES (:id, :ws, :idea, 'awaiting_user', CAST(:interrupt AS jsonb))"
            ),
            {
                "id": run_id,
                "ws": caller.workspace_id,
                "idea": idea_id,
                "interrupt": json.dumps(SPEC_REVIEW),
            },
        )
    return run_id


async def spec_confirmed_events(engine: AsyncEngine, caller: Caller) -> list[dict[str, Any]]:
    """The workspace's ``SpecConfirmed`` payloads, oldest first (read as the DB owner)."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT payload FROM core.outbox WHERE workspace_id = :ws "
                "AND type = 'SpecConfirmed' ORDER BY id"
            ),
            {"ws": caller.workspace_id},
        )
    return [dict(row[0]) for row in result]


async def idea_row(engine: AsyncEngine, idea_id: str) -> dict[str, Any]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT stage, kind, confirmed_spec_version_id FROM ideas.ideas WHERE id = :id"
                ),
                {"id": idea_id},
            )
        ).one()
    return {"stage": row[0], "kind": row[1], "confirmed": row[2]}
