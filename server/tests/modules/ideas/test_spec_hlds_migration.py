"""Migration ``0029_spec_hlds``: grants (insert and read only), RLS, constraints, one HLD per
spec version and the downgrade."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.helpers.ids import uuid7
from tests.helpers.auth import APP_ROLE
from tests.helpers.migrations import load_migration
from tests.modules.research.research_helpers import Run, new_run

MIGRATION = load_migration("0029_spec_hlds.py")


async def _scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return await conn.scalar(text(sql), params)


async def _hld(engine: AsyncEngine, run: Run, **fields: Any) -> Any:
    values: dict[str, Any] = {"number": 1, "language": "Python", "content": "## Overview", **fields}
    hld_id = uuid7()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ideas.spec_hlds "
                "(id, workspace_id, idea_id, spec_version_number, spec_hash, build_language, "
                "content_md) VALUES (:id, :ws, :idea, :number, 'h', :language, :content)"
            ),
            {"id": hld_id, "ws": run.workspace_id, "idea": run.idea_id, **values},
        )
    return hld_id


async def test_the_table_has_forced_row_level_security(engine: AsyncEngine) -> None:
    enabled = await _scalar(
        engine,
        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
        "WHERE oid = 'ideas.spec_hlds'::regclass",
    )

    assert enabled is True


@pytest.mark.parametrize(
    ("privilege", "allowed"),
    [("SELECT", True), ("INSERT", True), ("UPDATE", False), ("DELETE", False)],
)
async def test_metis_app_can_read_and_insert_but_never_change_or_delete_an_hld(
    engine: AsyncEngine, privilege: str, allowed: bool
) -> None:
    result = await _scalar(
        engine,
        "SELECT has_table_privilege(:role, 'ideas.spec_hlds', :privilege)",
        role=APP_ROLE,
        privilege=privilege,
    )

    assert result is allowed


async def test_the_app_role_cannot_update_or_delete_an_hld_row(engine: AsyncEngine) -> None:
    run = await new_run(engine)
    hld_id = await _hld(engine, run)

    for sql in (
        "UPDATE ideas.spec_hlds SET content_md = 'x' WHERE id = :id",
        "DELETE FROM ideas.spec_hlds WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with engine.begin() as conn:
                await conn.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
                await conn.execute(text(sql), {"id": hld_id})


async def test_a_workspace_sees_only_its_own_hlds(engine: AsyncEngine) -> None:
    ada = await new_run(engine, "ada")
    grace = await new_run(engine, "grace")
    await _hld(engine, ada)

    async with engine.begin() as conn:
        await conn.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        await conn.execute(
            text("SELECT set_config('app.workspace_id', :ws, true)"),
            {"ws": str(grace.workspace_id)},
        )
        count = await conn.scalar(text("SELECT count(*) FROM ideas.spec_hlds"))

    assert count == 0


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"number": 0}, "ck_spec_hlds_number"),
        ({"language": ""}, "ck_spec_hlds_build_language"),
        ({"language": "x" * 101}, "ck_spec_hlds_build_language"),
        ({"content": ""}, "ck_spec_hlds_content"),
    ],
)
async def test_the_table_refuses_bad_values(
    engine: AsyncEngine, fields: dict[str, Any], constraint: str
) -> None:
    run = await new_run(engine)

    with pytest.raises(IntegrityError, match=constraint):
        await _hld(engine, run, **fields)


async def test_a_spec_version_has_at_most_one_hld(engine: AsyncEngine) -> None:
    run = await new_run(engine)
    await _hld(engine, run)
    await _hld(engine, run, number=2)

    with pytest.raises(IntegrityError, match="uq_spec_hlds_idea_number"):
        await _hld(engine, run)


def test_the_revision_follows_the_idea_project_name_migration() -> None:
    assert MIGRATION.down_revision == "0028_idea_project_name"


async def test_the_downgrade_drops_the_table(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("DROP TABLE ideas.spec_hlds"))
        assert await conn.scalar(text("SELECT to_regclass('ideas.spec_hlds')")) is None
        await conn.rollback()
