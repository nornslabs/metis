"""Tests for PostgreSQL Row-Level Security (RLS) isolation.

This test validates that:
1. Tables with RLS enabled only return rows belonging to the current workspace
2. The app.workspace_id session variable is properly set and used
3. Workspace A cannot read Workspace B's data

Run with: uv run pytest server/tests/core/test_rls.py -v
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def get_database_url() -> str:
    """Get database URL from environment or default."""
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/metis_test",
    )


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires test database with RLS enabled")
async def test_workspace_a_cannot_read_workspace_b() -> None:
    """Workspace A should not be able to read Workspace B's rows.

    This test proves that RLS is working correctly by:
    1. Inserting rows into both workspaces
    2. Setting app.workspace_id to workspace_a
    3. Verifying only workspace_a rows are returned
    """
    engine = create_async_engine(get_database_url())

    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS test_rls"))
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS test_rls.test_tenant_items (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    workspace_id UUID NOT NULL,
                    name VARCHAR(100) NOT NULL
                )
                """
            )
        )
        await conn.execute(
            text("ALTER TABLE test_rls.test_tenant_items ENABLE ROW LEVEL SECURITY")
        )
        await conn.execute(
            text("ALTER TABLE test_rls.test_tenant_items FORCE ROW LEVEL SECURITY")
        )
        await conn.execute(
            text(
                """
                CREATE OR REPLACE POLICY test_workspace_isolation
                ON test_rls.test_tenant_items
                FOR ALL
                USING (
                    workspace_id = current_setting('app.workspace_id')::uuid
                )
                """
            )
        )

    Session = async_sessionmaker(engine, expire_on_commit=False)

    ws_a = str(uuid.uuid4())
    ws_b = str(uuid.uuid4())

    async with Session() as session:
        # Insert test data for both workspaces
        await session.execute(
            text(
                "INSERT INTO test_rls.test_tenant_items (id, workspace_id, name) "
                "VALUES ('item-a-1', :ws, 'Item A1'), ('item-a-2', :ws, 'Item A2')"
            ),
            {"ws": ws_a},
        )
        await session.execute(
            text(
                "INSERT INTO test_rls.test_tenant_items (id, workspace_id, name) "
                "VALUES ('item-b-1', :ws, 'Item B1'), ('item-b-2', :ws, 'Item B2')"
            ),
            {"ws": ws_b},
        )
        await session.commit()

    # Query as workspace A - should only see A's rows
    async with Session() as session:
        await session.execute(text(f"SET LOCAL app.workspace_id = '{ws_a}'"))
        result = await session.execute(
            text("SELECT id, name FROM test_rls.test_tenant_items ORDER BY id")
        )
        rows = result.fetchall()

        assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}"
        ids = [row[0] for row in rows]
        assert "item-a-1" in ids, "item-a-1 should be visible to workspace A"
        assert "item-a-2" in ids, "item-a-2 should be visible to workspace A"
        assert "item-b-1" not in ids, "item-b-1 should NOT be visible to workspace A"
        assert "item-b-2" not in ids, "item-b-2 should NOT be visible to workspace A"

    # Cleanup
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS test_rls CASCADE"))

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires test database with RLS enabled")
async def test_no_workspace_set_returns_empty() -> None:
    """If no workspace_id is set in session, all rows should be hidden.

    When app.workspace_id is not set or is NULL, the policy
    workspace_id = current_setting('app.workspace_id')::uuid fails,
    returning no rows.
    """
    engine = create_async_engine(get_database_url())

    ws_id = str(uuid.uuid4())

    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS test_rls"))
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS test_rls.test_empty_check (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    workspace_id UUID NOT NULL,
                    value TEXT NOT NULL
                )
                """
            )
        )
        await conn.execute(
            text("ALTER TABLE test_rls.test_empty_check ENABLE ROW LEVEL SECURITY")
        )
        await conn.execute(
            text("ALTER TABLE test_rls.test_empty_check FORCE ROW LEVEL SECURITY")
        )
        await conn.execute(
            text(
                """
                CREATE OR REPLACE POLICY test_empty_workspace_check
                ON test_rls.test_empty_check
                FOR ALL
                USING (workspace_id = current_setting('app.workspace_id')::uuid)
                """
            )
        )

    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        await session.execute(
            text(
                "INSERT INTO test_rls.test_empty_check (id, workspace_id, value) "
                "VALUES ('row-1', :ws, 'Test Row')"
            ),
            {"ws": ws_id},
        )
        await session.commit()

    # Query without setting workspace_id - should return empty
    async with Session() as session:
        result = await session.execute(
            text("SELECT * FROM test_rls.test_empty_check")
        )
        rows = result.fetchall()

        assert len(rows) == 0, "Expected no rows when workspace_id is not set"

    # Cleanup
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS test_rls CASCADE"))

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires test database with RLS enabled")
async def test_enable_tenant_rls_helper_works() -> None:
    """Verify the enable_tenant_rls() function works correctly.

    This test ensures the helper function created in migration 0001
    can be called without error.
    """
    engine = create_async_engine(get_database_url())

    ws_a = str(uuid.uuid4())
    ws_b = str(uuid.uuid4())

    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS test_rls"))
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS test_rls.test_helper_table ("
                "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
                "workspace_id UUID NOT NULL, "
                "value TEXT NOT NULL"
                ")"
            )
        )
        # Call the helper function (created in migration 0001)
        await conn.execute(
            text("SELECT enable_tenant_rls('test_rls.test_helper_table'::regclass)")
        )

    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        await session.execute(text(f"SET LOCAL app.workspace_id = '{ws_a}'"))

        # Insert via workspace A
        await session.execute(
            text(
                "INSERT INTO test_rls.test_helper_table (id, workspace_id, value) "
                "VALUES ('h-1', :ws, 'Workspace A')"
            ),
            {"ws": ws_a},
        )
        await session.commit()

    # Query as workspace B - should not see A's data
    async with Session() as session:
        await session.execute(text(f"SET LOCAL app.workspace_id = '{ws_b}'"))
        result = await session.execute(
            text("SELECT * FROM test_rls.test_helper_table")
        )
        rows = result.fetchall()

        assert len(rows) == 0, "RLS should hide workspace A's data from workspace B"

    # Cleanup
    async with engine.begin() as conn:
        await conn.execute(
            text("DROP TABLE IF EXISTS test_rls.test_helper_table CASCADE")
        )
        await conn.execute(text("DROP SCHEMA IF EXISTS test_rls CASCADE"))

    await engine.dispose()