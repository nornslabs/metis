"""Migration ``0016_research``: grants, RLS, constraints and indexes of the research tables,
and the downgrade (replayed in a rolled-back transaction)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.helpers.ids import uuid7
from tests.helpers.auth import APP_ROLE
from tests.helpers.migrations import load_migration
from tests.modules.research.research_helpers import Run, new_run

MIGRATION = load_migration("0016_research.py")
TABLES = ("snapshots", "items", "competitors", "idea_competitors")


async def _scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return await conn.scalar(text(sql), params)


async def _execute(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(sql), params)


async def _snapshot(engine: AsyncEngine, run: Run, closed: bool = False) -> UUID:
    snapshot_id = uuid7()
    await _execute(
        engine,
        "INSERT INTO research.snapshots (id, workspace_id, idea_id, run_id, closed_at) "
        "VALUES (:id, :ws, :idea, :run, CASE WHEN :closed THEN now() END)",
        id=snapshot_id,
        ws=run.workspace_id,
        idea=run.idea_id,
        run=run.run_id,
        closed=closed,
    )
    return snapshot_id


async def _item(engine: AsyncEngine, run: Run, snapshot_id: UUID, **fields: Any) -> None:
    values = {"kind": "market_fact", "url": "https://example.com", "confidence": 0.5, **fields}
    await _execute(
        engine,
        "INSERT INTO research.items "
        "(id, workspace_id, snapshot_id, kind, title, url, claim, confidence) "
        "VALUES (:id, :ws, :snap, :kind, 'T', :url, 'C', :confidence)",
        id=uuid7(),
        ws=run.workspace_id,
        snap=snapshot_id,
        **values,
    )


async def _competitor(engine: AsyncEngine, run: Run, domain: str) -> None:
    await _execute(
        engine,
        "INSERT INTO research.competitors (id, workspace_id, name, url, domain) "
        "VALUES (:id, :ws, 'Acme', 'https://acme.com', :domain)",
        id=uuid7(),
        ws=run.workspace_id,
        domain=domain,
    )


@pytest.mark.parametrize("table", TABLES)
async def test_every_table_has_forced_row_level_security(engine: AsyncEngine, table: str) -> None:
    enabled = await _scalar(
        engine,
        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
        f"WHERE oid = 'research.{table}'::regclass",
    )

    assert enabled is True


@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("privilege", ["SELECT", "INSERT", "UPDATE", "DELETE"])
async def test_metis_app_can_use_every_table(
    engine: AsyncEngine, table: str, privilege: str
) -> None:
    allowed = await _scalar(
        engine,
        "SELECT has_table_privilege(:role, :table, :privilege)",
        role=APP_ROLE,
        table=f"research.{table}",
        privilege=privilege,
    )

    assert allowed is True


@pytest.mark.parametrize("kind", ["competitor", "market_fact"])
async def test_competitor_and_market_fact_items_need_a_url(engine: AsyncEngine, kind: str) -> None:
    run = await new_run(engine)
    snapshot_id = await _snapshot(engine, run)

    with pytest.raises(IntegrityError, match="ck_items_source_url"):
        await _item(engine, run, snapshot_id, kind=kind, url=None)


async def test_items_refuse_unknown_kinds_and_out_of_range_confidence(engine: AsyncEngine) -> None:
    run = await new_run(engine)
    snapshot_id = await _snapshot(engine, run)

    await _item(engine, run, snapshot_id, kind="risk", url=None)
    with pytest.raises(IntegrityError, match="ck_items_kind"):
        await _item(engine, run, snapshot_id, kind="rumour")
    with pytest.raises(IntegrityError, match="ck_items_confidence"):
        await _item(engine, run, snapshot_id, confidence=1.5)


async def test_a_domain_is_unique_per_workspace(engine: AsyncEngine) -> None:
    ada = await new_run(engine, "ada")
    grace = await new_run(engine, "grace")
    await _competitor(engine, ada, "acme.com")
    await _competitor(engine, grace, "acme.com")

    with pytest.raises(IntegrityError, match="uq_competitors_workspace_domain"):
        await _competitor(engine, ada, "acme.com")


async def test_a_run_has_at_most_one_open_snapshot(engine: AsyncEngine) -> None:
    run = await new_run(engine)
    await _snapshot(engine, run, closed=True)
    await _snapshot(engine, run)

    with pytest.raises(IntegrityError, match=MIGRATION.OPEN_SNAPSHOT_INDEX):
        await _snapshot(engine, run)


async def test_competitor_embeddings_are_1536_dimension_vectors_with_an_index(
    engine: AsyncEngine,
) -> None:
    column_type = await _scalar(
        engine,
        "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
        "WHERE attrelid = 'research.competitors'::regclass AND attname = 'embedding'",
    )
    index = await _scalar(
        engine, "SELECT indexdef FROM pg_indexes WHERE indexname = :name", name=MIGRATION.HNSW_INDEX
    )

    assert column_type == "vector(1536)"
    assert "hnsw" in index and "vector_cosine_ops" in index


async def test_the_downgrade_drops_the_tables_and_keeps_the_schema(engine: AsyncEngine) -> None:
    assert MIGRATION.down_revision == "0015_interview_turns"

    async with engine.connect() as conn:
        for table in reversed(TABLES):
            await conn.execute(text(f"DROP TABLE research.{table}"))
        for statement in MIGRATION.SCHEMA_DOWN_SQL:
            await conn.execute(text(statement))
        assert await conn.scalar(text("SELECT to_regclass('research.snapshots')")) is None
        usage = await conn.scalar(
            text("SELECT has_schema_privilege(:role, 'research', 'USAGE')"), {"role": APP_ROLE}
        )
        assert usage is False
        await conn.rollback()
