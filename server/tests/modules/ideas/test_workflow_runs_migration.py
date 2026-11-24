"""Migration ``0013_workflow_runs``: the table's constraints, RLS, grants, the scan function
and the downgrade (replayed in a rolled-back transaction: DDL is transactional in Postgres)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.agent.llm_helpers import make_run, workspace_without_key
from tests.helpers.auth import APP_ROLE
from tests.helpers.migrations import load_migration

MIGRATION = "0013_workflow_runs.py"


async def _scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return await conn.scalar(text(sql), params)


async def test_the_table_has_forced_row_level_security(engine: AsyncEngine) -> None:
    enabled = await _scalar(
        engine,
        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
        "WHERE oid = 'ideas.workflow_runs'::regclass",
    )

    assert enabled is True


@pytest.mark.parametrize("privilege", ["SELECT", "INSERT", "UPDATE", "DELETE"])
async def test_metis_app_can_use_the_table(engine: AsyncEngine, privilege: str) -> None:
    allowed = await _scalar(
        engine,
        "SELECT has_table_privilege(:role, 'ideas.workflow_runs', :privilege)",
        role=APP_ROLE,
        privilege=privilege,
    )

    assert allowed is True


@pytest.mark.parametrize(("column", "value"), [("status", "paused"), ("kind", "watch")])
async def test_the_table_refuses_unknown_statuses_and_kinds(
    engine: AsyncEngine, column: str, value: str
) -> None:
    workspace_id = await workspace_without_key(engine)
    run_id = await make_run(engine, workspace_id)

    async with engine.connect() as conn:
        with pytest.raises(IntegrityError, match="ck_workflow_runs"):
            await conn.execute(
                text(f"UPDATE ideas.workflow_runs SET {column} = :v WHERE id = :id"),
                {"v": value, "id": run_id},
            )
        await conn.rollback()


async def test_the_scan_function_is_executable_by_the_app_role_only(engine: AsyncEngine) -> None:
    app_can = await _scalar(
        engine,
        "SELECT has_function_privilege(:role, 'ideas.list_running_runs()', 'EXECUTE')",
        role=APP_ROLE,
    )
    public_can = await _scalar(
        engine,
        "SELECT has_function_privilege('public', 'ideas.list_running_runs()', 'EXECUTE')",
    )

    assert (app_can, public_can) == (True, False)  # noqa: FBT003


async def test_the_app_role_cannot_read_runs_without_a_workspace(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    workspace_id = await workspace_without_key(engine)
    await make_run(engine, workspace_id)

    async with app_sessions() as session:
        visible = await session.scalar(text("SELECT count(*) FROM ideas.workflow_runs"))

    assert visible == 0


async def test_the_downgrade_drops_the_function_the_key_and_the_table(engine: AsyncEngine) -> None:
    migration = load_migration(MIGRATION)
    assert migration.down_revision == "0012_agent_checkpoints"

    async with engine.connect() as conn:
        # 0021's plans reference 0020's spec versions, which reference runs; 0017's score
        # tables, 0016's research tables and 0015's interview turns reference runs too.
        # 0024's export jobs reference plans, ideas and runs.
        await conn.execute(text("DROP TABLE integrations.export_jobs"))
        for table in ("task_deps", "tasks", "phases", "plans"):
            await conn.execute(text(f"DROP TABLE planning.{table}"))
        await conn.execute(text("ALTER TABLE ideas.ideas DROP COLUMN confirmed_spec_version_id"))
        await conn.execute(text("DROP TABLE ideas.spec_versions"))
        for table in ("suggestions", "score_params", "score_runs"):
            await conn.execute(text(f"DROP TABLE scoring.{table}"))
        for table in ("idea_competitors", "items", "competitors", "snapshots"):
            await conn.execute(text(f"DROP TABLE research.{table}"))
        await conn.execute(text("DROP TABLE ideas.interview_turns"))
        for statement in migration.FUNCTION_DOWN_SQL:
            await conn.execute(text(statement))
        await conn.execute(
            text(f"ALTER TABLE ideas.llm_usage DROP CONSTRAINT {migration.USAGE_FK}")
        )
        await conn.execute(text("DROP TABLE ideas.workflow_runs"))
        assert await conn.scalar(text("SELECT to_regclass('ideas.workflow_runs')")) is None
        assert await conn.scalar(text("SELECT to_regclass('ideas.llm_usage')")) is not None
        with pytest.raises(ProgrammingError):
            await conn.execute(text("SELECT * FROM ideas.list_running_runs()"))
        await conn.rollback()
