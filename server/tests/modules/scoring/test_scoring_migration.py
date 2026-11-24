"""Migration ``0017_scoring``: seeded rubric, grants (read and insert only), RLS, constraints
and the downgrade (replayed in a rolled-back transaction)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.helpers.ids import uuid7
from tests.helpers.auth import APP_ROLE
from tests.helpers.migrations import load_migration
from tests.modules.research.research_helpers import Run, new_run

if TYPE_CHECKING:
    from uuid import UUID

MIGRATION = load_migration("0017_scoring.py")
TENANT_TABLES = ("score_runs", "score_params")


async def _scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return await conn.scalar(text(sql), params)


async def _execute(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(sql), params)


async def _score_run(engine: AsyncEngine, run: Run, **fields: Any) -> UUID:
    values = {"trigger": "manual", "total": 60, "band": "promising", **fields}
    score_run_id = uuid7()
    await _execute(
        engine,
        "INSERT INTO scoring.score_runs "
        "(id, workspace_id, idea_id, run_id, rubric_version_id, trigger, total, band) "
        "VALUES (:id, :ws, :idea, :run, 1, :trigger, :total, :band)",
        id=score_run_id,
        ws=run.workspace_id,
        idea=run.idea_id,
        run=run.run_id,
        **values,
    )
    return score_run_id


async def _param(engine: AsyncEngine, run: Run, score_run_id: UUID, **fields: Any) -> None:
    values = {
        "param": "value",
        "raw": 5,
        "confidence": 0.5,
        "no_evidence": False,
        "evidence": '[{"url": "https://example.com", "title": "T", "quote": ""}]',
        **fields,
    }
    await _execute(
        engine,
        "INSERT INTO scoring.score_params (score_run_id, workspace_id, param, raw, weighted, "
        "reason, confidence, no_evidence, evidence) "
        "VALUES (:sr, :ws, :param, :raw, 5, 'R', :confidence, :no_evidence, "
        "CAST(:evidence AS jsonb))",
        sr=score_run_id,
        ws=run.workspace_id,
        **values,
    )


async def test_version_1_of_the_rubric_is_seeded_with_the_fixed_weights(
    engine: AsyncEngine,
) -> None:
    weights = await _scalar(engine, "SELECT weights FROM scoring.rubric_versions WHERE id = 1")

    assert weights == {
        "problem_severity": 25,
        "uniqueness": 25,
        "market_demand": 15,
        "value": 15,
        "feasibility": 10,
        "timing": 10,
    }
    assert sum(weights.values()) == 100


@pytest.mark.parametrize("table", TENANT_TABLES)
async def test_tenant_tables_have_forced_row_level_security(
    engine: AsyncEngine, table: str
) -> None:
    enabled = await _scalar(
        engine,
        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
        f"WHERE oid = 'scoring.{table}'::regclass",
    )

    assert enabled is True


@pytest.mark.parametrize("table", TENANT_TABLES)
@pytest.mark.parametrize(
    ("privilege", "allowed"),
    [("SELECT", True), ("INSERT", True), ("UPDATE", False), ("DELETE", False)],
)
async def test_metis_app_can_only_read_and_insert_score_tables(
    engine: AsyncEngine, table: str, privilege: str, allowed: bool
) -> None:
    result = await _scalar(
        engine,
        "SELECT has_table_privilege(:role, :table, :privilege)",
        role=APP_ROLE,
        table=f"scoring.{table}",
        privilege=privilege,
    )

    assert result is allowed


async def test_metis_app_can_only_read_the_rubric(engine: AsyncEngine) -> None:
    privileges = {
        p: await _scalar(
            engine,
            "SELECT has_table_privilege(:role, 'scoring.rubric_versions', :p)",
            role=APP_ROLE,
            p=p,
        )
        for p in ("SELECT", "INSERT", "UPDATE", "DELETE")
    }

    assert privileges == {"SELECT": True, "INSERT": False, "UPDATE": False, "DELETE": False}


async def test_the_app_role_cannot_update_or_delete_a_score_run(engine: AsyncEngine) -> None:
    run = await new_run(engine)
    score_run_id = await _score_run(engine, run)

    for sql in (
        "UPDATE scoring.score_runs SET total = 99 WHERE id = :id",
        "DELETE FROM scoring.score_runs WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with engine.begin() as conn:
                await conn.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
                await conn.execute(text(sql), {"id": score_run_id})


async def test_a_workspace_sees_only_its_own_score_runs(engine: AsyncEngine) -> None:
    ada = await new_run(engine, "ada")
    grace = await new_run(engine, "grace")
    await _score_run(engine, ada)

    async with engine.begin() as conn:
        await conn.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        await conn.execute(
            text("SELECT set_config('app.workspace_id', :ws, true)"),
            {"ws": str(grace.workspace_id)},
        )
        count = await conn.scalar(text("SELECT count(*) FROM scoring.score_runs"))

    assert count == 0


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"trigger": "whenever"}, "ck_score_runs_trigger"),
        ({"total": 101}, "ck_score_runs_total"),
        ({"total": -1}, "ck_score_runs_total"),
        ({"band": "great"}, "ck_score_runs_band"),
    ],
)
async def test_score_runs_refuse_bad_values(
    engine: AsyncEngine, fields: dict[str, Any], constraint: str
) -> None:
    run = await new_run(engine)

    with pytest.raises(IntegrityError, match=constraint):
        await _score_run(engine, run, **fields)


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"param": "luck"}, "ck_score_params_param"),
        ({"raw": 11}, "ck_score_params_raw"),
        ({"raw": -1}, "ck_score_params_raw"),
        ({"confidence": 1.5}, "ck_score_params_confidence"),
        ({"evidence": "[]", "no_evidence": False}, "ck_score_params_evidence_flag"),
        ({"no_evidence": True}, "ck_score_params_evidence_flag"),
        ({"evidence": "{}"}, "ck_score_params_evidence_flag"),
    ],
)
async def test_score_params_refuse_bad_values(
    engine: AsyncEngine, fields: dict[str, Any], constraint: str
) -> None:
    run = await new_run(engine)
    score_run_id = await _score_run(engine, run)

    with pytest.raises(IntegrityError, match=constraint):
        await _param(engine, run, score_run_id, **fields)


async def test_a_parameter_is_unique_within_a_score_run(engine: AsyncEngine) -> None:
    run = await new_run(engine)
    score_run_id = await _score_run(engine, run)
    await _param(engine, run, score_run_id)

    with pytest.raises(IntegrityError, match="pk_score_params"):
        await _param(engine, run, score_run_id)


async def test_the_downgrade_drops_the_tables_and_keeps_the_schema(engine: AsyncEngine) -> None:
    assert MIGRATION.down_revision == "0016_research"

    async with engine.connect() as conn:
        for table in ("suggestions", "score_params", "score_runs", "rubric_versions"):
            await conn.execute(text(f"DROP TABLE scoring.{table}"))
        for statement in MIGRATION.SCHEMA_DOWN_SQL:
            await conn.execute(text(statement))
        assert await conn.scalar(text("SELECT to_regclass('scoring.score_runs')")) is None
        usage = await conn.scalar(
            text("SELECT has_schema_privilege(:role, 'scoring', 'USAGE')"), {"role": APP_ROLE}
        )
        assert usage is False
        await conn.rollback()
