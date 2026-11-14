"""Tenant row-level security through the ``enable_tenant_rls`` helper.

Seam: the helper from migration ``0001_initial`` on a migrated Postgres,
observed only through which rows a non-superuser session can read or write.
Superusers bypass RLS even when it is forced, so every query runs as the
``NOLOGIN NOSUPERUSER`` role this fixture creates.

Set ``TEST_DATABASE_URL`` to a database migrated with ``alembic upgrade head``.
Tests skip only when Postgres is unreachable or the helper is missing.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/metis"
)
TEST_SCHEMA = "test_rls"
TEST_ROLE = "metis_rls_test"
TENANT_TABLE = f"{TEST_SCHEMA}.tenant_items"

WORKSPACE_A = uuid4()
WORKSPACE_B = uuid4()

_CREATE_TEST_ROLE = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{TEST_ROLE}') THEN
        CREATE ROLE {TEST_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END
$$
"""


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """A migrated database with a fresh tenant table set up by the helper."""
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            helper = await conn.scalar(
                text("SELECT to_regprocedure('enable_tenant_rls(regclass)') IS NOT NULL")
            )
    except Exception:  # noqa: BLE001
        await engine.dispose()
        pytest.skip("Postgres not reachable")
    if not helper:
        await engine.dispose()
        pytest.skip("enable_tenant_rls missing; run `alembic upgrade head`")

    async with engine.begin() as conn:
        await conn.execute(text(_CREATE_TEST_ROLE))
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {TEST_SCHEMA}"))
        await conn.execute(
            text(
                f"CREATE TABLE {TENANT_TABLE} ("
                "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
                "workspace_id uuid NOT NULL, "
                "name text NOT NULL)"
            )
        )
        await conn.execute(text(f"SELECT enable_tenant_rls('{TENANT_TABLE}'::regclass)"))
        await conn.execute(text(f"GRANT USAGE ON SCHEMA {TEST_SCHEMA} TO {TEST_ROLE}"))
        await conn.execute(text(f"GRANT SELECT, INSERT ON {TENANT_TABLE} TO {TEST_ROLE}"))
        # Seeded as the table owner (a superuser), which bypasses RLS.
        await conn.execute(
            text(f"INSERT INTO {TENANT_TABLE} (workspace_id, name) VALUES (:ws, :name)"),
            [
                {"ws": WORKSPACE_A, "name": "a-1"},
                {"ws": WORKSPACE_A, "name": "a-2"},
                {"ws": WORKSPACE_B, "name": "b-1"},
            ],
        )

    yield engine

    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE"))
    await engine.dispose()


async def _as_tenant(conn: AsyncConnection, workspace_id: UUID | None) -> None:
    """Switch the current transaction to the test role and, optionally, a workspace."""
    await conn.execute(text(f"SET LOCAL ROLE {TEST_ROLE}"))
    if workspace_id is not None:
        await conn.execute(
            text("SELECT set_config('app.workspace_id', :ws, true)"),
            {"ws": str(workspace_id)},
        )


async def _visible_names(engine: AsyncEngine, workspace_id: UUID | None) -> list[str]:
    async with engine.begin() as conn:
        await _as_tenant(conn, workspace_id)
        result = await conn.execute(text(f"SELECT name FROM {TENANT_TABLE} ORDER BY name"))
        return list(result.scalars())


@pytest.mark.asyncio
async def test_workspace_a_cannot_read_workspace_b(engine: AsyncEngine) -> None:
    assert await _visible_names(engine, WORKSPACE_A) == ["a-1", "a-2"]
    assert await _visible_names(engine, WORKSPACE_B) == ["b-1"]


@pytest.mark.asyncio
async def test_no_workspace_set_returns_empty(engine: AsyncEngine) -> None:
    assert await _visible_names(engine, None) == []

    # A pooled connection that had a workspace in an earlier transaction reads the
    # setting back as '' afterwards; that must still fail closed, not raise.
    async with engine.connect() as conn:
        async with conn.begin():
            await _as_tenant(conn, WORKSPACE_A)
        async with conn.begin():
            await _as_tenant(conn, None)
            rows = await conn.execute(text(f"SELECT name FROM {TENANT_TABLE}"))
            assert list(rows.scalars()) == []


@pytest.mark.asyncio
async def test_enable_tenant_rls_helper_blocks_cross_workspace_writes(
    engine: AsyncEngine,
) -> None:
    async with engine.begin() as conn:
        await _as_tenant(conn, WORKSPACE_A)
        await conn.execute(
            text(f"INSERT INTO {TENANT_TABLE} (workspace_id, name) VALUES (:ws, 'a-3')"),
            {"ws": WORKSPACE_A},
        )

    with pytest.raises(DBAPIError, match="row-level security"):
        async with engine.begin() as conn:
            await _as_tenant(conn, WORKSPACE_A)
            await conn.execute(
                text(f"INSERT INTO {TENANT_TABLE} (workspace_id, name) VALUES (:ws, 'x')"),
                {"ws": WORKSPACE_B},
            )

    assert await _visible_names(engine, WORKSPACE_A) == ["a-1", "a-2", "a-3"]
    assert await _visible_names(engine, WORKSPACE_B) == ["b-1"]


@pytest.mark.asyncio
async def test_isolation_assertion_fails_when_rls_is_removed(engine: AsyncEngine) -> None:
    """Proves the isolation check is not vacuous: without RLS, B's rows leak to A."""
    async with engine.begin() as conn:
        await conn.execute(text(f"ALTER TABLE {TENANT_TABLE} DISABLE ROW LEVEL SECURITY"))

    assert await _visible_names(engine, WORKSPACE_A) == ["a-1", "a-2", "b-1"]

    async with engine.begin() as conn:
        await conn.execute(text(f"ALTER TABLE {TENANT_TABLE} ENABLE ROW LEVEL SECURITY"))

    assert await _visible_names(engine, WORKSPACE_A) == ["a-1", "a-2"]
