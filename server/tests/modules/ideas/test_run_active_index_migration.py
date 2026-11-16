"""Migration ``0014_run_active_index``: one active run per idea, enforced by Postgres."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.agent.llm_helpers import make_run, workspace_without_key
from tests.helpers.migrations import load_migration

MIGRATION = load_migration("0014_run_active_index.py")


async def _add_run(engine: AsyncEngine, workspace_id: str, idea_id: str, status: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ideas.workflow_runs (id, workspace_id, idea_id, status) "
                "VALUES (:id, :ws, :idea, :status)"
            ),
            {"id": uuid4(), "ws": workspace_id, "idea": idea_id, "status": status},
        )


async def _idea_of(engine: AsyncEngine, run_id: object) -> tuple[str, str]:
    async with engine.connect() as conn:
        row = await conn.execute(
            text("SELECT idea_id, workspace_id FROM ideas.workflow_runs WHERE id = :id"),
            {"id": run_id},
        )
        idea_id, workspace_id = row.one()
    return str(idea_id), str(workspace_id)


async def test_the_index_is_unique_and_limited_to_active_statuses(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        definition = await conn.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
            {"name": MIGRATION.INDEX},
        )

    assert definition is not None
    assert "UNIQUE" in definition
    assert "(idea_id)" in definition
    assert all(status in definition for status in MIGRATION.ACTIVE_STATUSES)
    assert "succeeded" not in definition


@pytest.mark.parametrize("status", MIGRATION.ACTIVE_STATUSES)
async def test_a_second_active_run_on_one_idea_is_refused(engine: AsyncEngine, status: str) -> None:
    workspace_id = await workspace_without_key(engine)
    idea_id, _ = await _idea_of(engine, await make_run(engine, workspace_id))

    with pytest.raises(IntegrityError, match=MIGRATION.INDEX):
        await _add_run(engine, str(workspace_id), idea_id, status)


@pytest.mark.parametrize("status", ["succeeded", "failed", "cancelled"])
async def test_finished_runs_do_not_count(engine: AsyncEngine, status: str) -> None:
    workspace_id = await workspace_without_key(engine)
    idea_id, _ = await _idea_of(engine, await make_run(engine, workspace_id))

    await _add_run(engine, str(workspace_id), idea_id, status)
    await _add_run(engine, str(workspace_id), idea_id, status)
