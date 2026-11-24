"""Migration ``0018_manual_refresh_runs`` extends persisted run kinds."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.agent.llm_helpers import make_run, workspace_without_key


@pytest.mark.parametrize("kind", ["rescore", "market_recheck"])
async def test_manual_refresh_kinds_are_allowed(engine: AsyncEngine, kind: str) -> None:
    workspace_id = await workspace_without_key(engine)
    run_id = await make_run(engine, workspace_id)
    async with engine.connect() as conn:
        idea_id = await conn.scalar(
            text("SELECT idea_id FROM ideas.workflow_runs WHERE id = :id"), {"id": run_id}
        )
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ideas.workflow_runs "
                "(id, workspace_id, idea_id, kind, status) "
                "VALUES (:id, :workspace_id, :idea_id, :kind, 'succeeded')"
            ),
            {
                "id": uuid4(),
                "workspace_id": workspace_id,
                "idea_id": idea_id,
                "kind": kind,
            },
        )


async def test_unknown_run_kind_is_rejected(engine: AsyncEngine) -> None:
    workspace_id = await workspace_without_key(engine)
    run_id = await make_run(engine, workspace_id)
    async with engine.connect() as conn:
        idea_id = await conn.scalar(
            text("SELECT idea_id FROM ideas.workflow_runs WHERE id = :id"), {"id": run_id}
        )
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO ideas.workflow_runs "
                    "(id, workspace_id, idea_id, kind, status) "
                    "VALUES (:id, :workspace_id, :idea_id, 'invalid', 'succeeded')"
                ),
                {"id": uuid4(), "workspace_id": workspace_id, "idea_id": idea_id},
            )
