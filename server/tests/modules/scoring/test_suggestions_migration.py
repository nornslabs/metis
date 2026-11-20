"""Migration ``0018_suggestions``: grants (status is the only column the app role may change),
RLS, constraints, the merge of the two 0017 heads and the downgrade."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.helpers.ids import uuid7
from tests.helpers.auth import APP_ROLE
from tests.helpers.migrations import load_migration
from tests.modules.research.research_helpers import Run, new_run

MIGRATION = load_migration("0018_suggestions.py")
EVIDENCE = json.dumps([{"url": "https://example.com", "title": "T", "quote": ""}])


async def _scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return await conn.scalar(text(sql), params)


async def _execute(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(sql), params)


async def _score_run(engine: AsyncEngine, run: Run) -> UUID:
    score_run_id = uuid7()
    await _execute(
        engine,
        "INSERT INTO scoring.score_runs "
        "(id, workspace_id, idea_id, run_id, rubric_version_id, trigger, total, band) "
        "VALUES (:id, :ws, :idea, :run, 1, 'manual', 40, 'advise')",
        id=score_run_id,
        ws=run.workspace_id,
        idea=run.idea_id,
        run=run.run_id,
    )
    return score_run_id


async def _suggestion(engine: AsyncEngine, run: Run, score_run_id: UUID, **fields: Any) -> UUID:
    values: dict[str, Any] = {
        "kind": "niche",
        "target_params": ["uniqueness"],
        "evidence": EVIDENCE,
        "status": "open",
        **fields,
    }
    suggestion_id = uuid7()
    await _execute(
        engine,
        "INSERT INTO scoring.suggestions (id, workspace_id, idea_id, score_run_id, kind, title, "
        "rationale, target_params, expected_impact, evidence, status) "
        "VALUES (:id, :ws, :idea, :sr, :kind, 'T', 'R', CAST(:target_params AS text[]), 'I', "
        "CAST(:evidence AS jsonb), :status)",
        id=suggestion_id,
        ws=run.workspace_id,
        idea=run.idea_id,
        sr=score_run_id,
        **values,
    )
    return suggestion_id


async def test_the_table_has_forced_row_level_security(engine: AsyncEngine) -> None:
    enabled = await _scalar(
        engine,
        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
        "WHERE oid = 'scoring.suggestions'::regclass",
    )

    assert enabled is True


@pytest.mark.parametrize(
    ("privilege", "allowed"),
    [("SELECT", True), ("INSERT", True), ("UPDATE", False), ("DELETE", False)],
)
async def test_metis_app_can_read_and_insert_but_not_update_or_delete_a_whole_row(
    engine: AsyncEngine, privilege: str, allowed: bool
) -> None:
    result = await _scalar(
        engine,
        "SELECT has_table_privilege(:role, 'scoring.suggestions', :privilege)",
        role=APP_ROLE,
        privilege=privilege,
    )

    assert result is allowed


async def test_metis_app_can_update_only_the_status_column(engine: AsyncEngine) -> None:
    columns = ("status", "title", "rationale", "evidence", "target_params", "score_run_id")

    allowed = {
        column: await _scalar(
            engine,
            "SELECT has_column_privilege(:role, 'scoring.suggestions', :column, 'UPDATE')",
            role=APP_ROLE,
            column=column,
        )
        for column in columns
    }

    assert allowed == {column: column == "status" for column in columns}


async def test_the_app_role_cannot_change_a_suggestions_text_or_delete_it(
    engine: AsyncEngine,
) -> None:
    run = await new_run(engine)
    suggestion_id = await _suggestion(engine, run, await _score_run(engine, run))

    for sql in (
        "UPDATE scoring.suggestions SET title = 'Other' WHERE id = :id",
        "DELETE FROM scoring.suggestions WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with engine.begin() as conn:
                await conn.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
                await conn.execute(text(sql), {"id": suggestion_id})


async def test_a_workspace_sees_only_its_own_suggestions(engine: AsyncEngine) -> None:
    ada = await new_run(engine, "ada")
    grace = await new_run(engine, "grace")
    await _suggestion(engine, ada, await _score_run(engine, ada))

    async with engine.begin() as conn:
        await conn.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        await conn.execute(
            text("SELECT set_config('app.workspace_id', :ws, true)"),
            {"ws": str(grace.workspace_id)},
        )
        count = await conn.scalar(text("SELECT count(*) FROM scoring.suggestions"))

    assert count == 0


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"kind": "rewrite"}, "ck_suggestions_kind"),
        ({"status": "done"}, "ck_suggestions_status"),
        ({"target_params": []}, "ck_suggestions_target_params"),
        ({"target_params": ["luck"]}, "ck_suggestions_target_params"),
        (
            {"target_params": ["value", "timing", "uniqueness", "feasibility"]},
            "ck_suggestions_target_params",
        ),
        ({"evidence": "[]"}, "ck_suggestions_evidence"),
        ({"evidence": "{}"}, "ck_suggestions_evidence"),
    ],
)
async def test_the_table_refuses_bad_values(
    engine: AsyncEngine, fields: dict[str, Any], constraint: str
) -> None:
    run = await new_run(engine)
    score_run_id = await _score_run(engine, run)

    with pytest.raises(IntegrityError, match=constraint):
        await _suggestion(engine, run, score_run_id, **fields)


async def test_a_suggestion_goes_when_its_score_run_goes(engine: AsyncEngine) -> None:
    run = await new_run(engine)
    score_run_id = await _score_run(engine, run)
    await _suggestion(engine, run, score_run_id)

    await _execute(engine, "DELETE FROM scoring.score_runs WHERE id = :id", id=score_run_id)

    assert await _scalar(engine, "SELECT count(*) FROM scoring.suggestions") == 0


def test_the_revision_merges_the_two_heads_that_follow_0016() -> None:
    assert MIGRATION.down_revision == ("0017_scoring", "0017_run_user_prompt")


async def test_the_downgrade_drops_the_table(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("DROP TABLE scoring.suggestions"))
        assert await conn.scalar(text("SELECT to_regclass('scoring.suggestions')")) is None
        await conn.rollback()
