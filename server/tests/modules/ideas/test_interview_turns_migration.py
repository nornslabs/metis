"""Migration ``0015_interview_turns``: the table's constraints, RLS, grants, the one-open-question
index, the brief column and the downgrade (replayed in a rolled-back transaction)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.agent.llm_helpers import make_run, workspace_without_key
from tests.helpers.auth import APP_ROLE
from tests.helpers.migrations import load_migration

MIGRATION = load_migration("0015_interview_turns.py")


async def _scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return await conn.scalar(text(sql), params)


async def _run(engine: AsyncEngine) -> tuple[UUID, UUID, UUID]:
    """``(workspace_id, idea_id, run_id)`` of a fresh queued run."""
    workspace_id = await workspace_without_key(engine)
    run_id = await make_run(engine, workspace_id)
    idea_id = await _scalar(
        engine, "SELECT idea_id FROM ideas.workflow_runs WHERE id = :id", id=run_id
    )
    return workspace_id, idea_id, run_id


async def _add_turn(
    engine: AsyncEngine,
    ids: tuple[UUID, UUID, UUID],
    *,
    topic: str = "problem",
    source: str = "asked",
    answer: str | None = None,
) -> None:
    workspace_id, idea_id, run_id = ids
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ideas.interview_turns "
                "(id, workspace_id, idea_id, run_id, topic, source, question, answer) "
                "VALUES (:id, :ws, :idea, :run, :topic, :source, 'Why?', :answer)"
            ),
            {
                "id": uuid4(),
                "ws": workspace_id,
                "idea": idea_id,
                "run": run_id,
                "topic": topic,
                "source": source,
                "answer": answer,
            },
        )


async def test_the_table_has_forced_row_level_security(engine: AsyncEngine) -> None:
    enabled = await _scalar(
        engine,
        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
        "WHERE oid = 'ideas.interview_turns'::regclass",
    )

    assert enabled is True


@pytest.mark.parametrize("privilege", ["SELECT", "INSERT", "UPDATE", "DELETE"])
async def test_metis_app_can_use_the_table(engine: AsyncEngine, privilege: str) -> None:
    allowed = await _scalar(
        engine,
        "SELECT has_table_privilege(:role, 'ideas.interview_turns', :privilege)",
        role=APP_ROLE,
        privilege=privilege,
    )

    assert allowed is True


@pytest.mark.parametrize(("column", "value"), [("topic", "pricing"), ("source", "guessed")])
async def test_the_table_refuses_unknown_topics_and_sources(
    engine: AsyncEngine, column: str, value: str
) -> None:
    ids = await _run(engine)

    with pytest.raises(IntegrityError, match="ck_interview_turns"):
        await _add_turn(engine, ids, **{column: value})


async def test_a_run_has_at_most_one_unanswered_question(engine: AsyncEngine) -> None:
    ids = await _run(engine)
    await _add_turn(engine, ids)

    with pytest.raises(IntegrityError, match=MIGRATION.OPEN_QUESTION_INDEX):
        await _add_turn(engine, ids, topic="customer")


async def test_answered_questions_and_notes_do_not_count_as_open(engine: AsyncEngine) -> None:
    ids = await _run(engine)

    await _add_turn(engine, ids, answer="Freelancers lose leads.")
    await _add_turn(engine, ids, source="noted")
    await _add_turn(engine, ids, source="noted")
    await _add_turn(engine, ids)


async def test_ideas_have_a_nullable_brief_column(engine: AsyncEngine) -> None:
    _, idea_id, _ = await _run(engine)

    brief = await _scalar(
        engine, "SELECT interview_brief FROM ideas.ideas WHERE id = :id", id=idea_id
    )

    assert brief is None


async def test_the_downgrade_drops_the_column_and_the_table(engine: AsyncEngine) -> None:
    assert MIGRATION.down_revision == "0014_run_active_index"

    async with engine.connect() as conn:
        await conn.execute(text(f"ALTER TABLE ideas.ideas DROP COLUMN {MIGRATION.BRIEF_COLUMN}"))
        await conn.execute(text("DROP TABLE ideas.interview_turns"))
        assert await conn.scalar(text("SELECT to_regclass('ideas.interview_turns')")) is None
        assert await conn.scalar(text("SELECT to_regclass('ideas.workflow_runs')")) is not None
        await conn.rollback()
