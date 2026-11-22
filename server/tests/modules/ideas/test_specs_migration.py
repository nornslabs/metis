"""Migration ``0020_spec_versions``: grants (insert and read only), RLS, constraints, the one
agent draft per run and the downgrade."""

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

MIGRATION = load_migration("0020_spec_versions.py")


async def _scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return await conn.scalar(text(sql), params)


async def _version(engine: AsyncEngine, run: Run, **fields: Any) -> UUID:
    values: dict[str, Any] = {
        "number": 1,
        "source": "agent",
        "sections": json.dumps({}),
        "run_id": None,
        **fields,
    }
    version_id = uuid7()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ideas.spec_versions "
                "(id, workspace_id, idea_id, number, source, content_md, sections, run_id) "
                "VALUES (:id, :ws, :idea, :number, :source, '# Spec', "
                "CAST(:sections AS jsonb), :run_id)"
            ),
            {"id": version_id, "ws": run.workspace_id, "idea": run.idea_id, **values},
        )
    return version_id


async def test_the_table_has_forced_row_level_security(engine: AsyncEngine) -> None:
    enabled = await _scalar(
        engine,
        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
        "WHERE oid = 'ideas.spec_versions'::regclass",
    )

    assert enabled is True


@pytest.mark.parametrize(
    ("privilege", "allowed"),
    [("SELECT", True), ("INSERT", True), ("UPDATE", False), ("DELETE", False)],
)
async def test_metis_app_can_read_and_insert_but_never_change_or_delete_a_version(
    engine: AsyncEngine, privilege: str, allowed: bool
) -> None:
    result = await _scalar(
        engine,
        "SELECT has_table_privilege(:role, 'ideas.spec_versions', :privilege)",
        role=APP_ROLE,
        privilege=privilege,
    )

    assert result is allowed


async def test_the_app_role_cannot_update_or_delete_a_version_row(engine: AsyncEngine) -> None:
    run = await new_run(engine)
    version_id = await _version(engine, run)

    for sql in (
        "UPDATE ideas.spec_versions SET content_md = 'x' WHERE id = :id",
        "DELETE FROM ideas.spec_versions WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with engine.begin() as conn:
                await conn.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
                await conn.execute(text(sql), {"id": version_id})


async def test_a_workspace_sees_only_its_own_versions(engine: AsyncEngine) -> None:
    ada = await new_run(engine, "ada")
    grace = await new_run(engine, "grace")
    await _version(engine, ada)

    async with engine.begin() as conn:
        await conn.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        await conn.execute(
            text("SELECT set_config('app.workspace_id', :ws, true)"),
            {"ws": str(grace.workspace_id)},
        )
        count = await conn.scalar(text("SELECT count(*) FROM ideas.spec_versions"))

    assert count == 0


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"number": 0}, "ck_spec_versions_number"),
        ({"source": "model"}, "ck_spec_versions_source"),
        ({"sections": "[]"}, "ck_spec_versions_sections"),
    ],
)
async def test_the_table_refuses_bad_values(
    engine: AsyncEngine, fields: dict[str, Any], constraint: str
) -> None:
    run = await new_run(engine)

    with pytest.raises(IntegrityError, match=constraint):
        await _version(engine, run, **fields)


async def test_a_version_number_is_used_once_per_idea(engine: AsyncEngine) -> None:
    run = await new_run(engine)
    await _version(engine, run)

    with pytest.raises(IntegrityError, match="uq_spec_versions_idea_number"):
        await _version(engine, run)


async def test_a_run_drafts_at_most_one_agent_version_but_may_have_user_versions(
    engine: AsyncEngine,
) -> None:
    run = await new_run(engine)
    await _version(engine, run, number=1, run_id=run.run_id)
    await _version(engine, run, number=2, source="user", run_id=run.run_id)

    with pytest.raises(IntegrityError, match="uq_spec_versions_agent_run"):
        await _version(engine, run, number=3, run_id=run.run_id)


async def test_an_idea_has_no_confirmed_version_until_one_is_set(engine: AsyncEngine) -> None:
    run = await new_run(engine)
    version_id = await _version(engine, run)

    before = await _scalar(
        engine,
        "SELECT confirmed_spec_version_id FROM ideas.ideas WHERE id = :id",
        id=run.idea_id,
    )
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE ideas.ideas SET confirmed_spec_version_id = :v WHERE id = :id"),
            {"v": version_id, "id": run.idea_id},
        )

    assert before is None
    assert (
        await _scalar(
            engine,
            "SELECT confirmed_spec_version_id FROM ideas.ideas WHERE id = :id",
            id=run.idea_id,
        )
        == version_id
    )


def test_the_revision_follows_the_merge_of_the_manual_refresh_heads() -> None:
    assert MIGRATION.down_revision == "3aaa8e5afd8c"


async def test_the_downgrade_drops_the_column_and_the_table(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("ALTER TABLE ideas.ideas DROP COLUMN confirmed_spec_version_id"))
        await conn.execute(text("DROP TABLE ideas.spec_versions"))
        assert await conn.scalar(text("SELECT to_regclass('ideas.spec_versions')")) is None
        await conn.rollback()
