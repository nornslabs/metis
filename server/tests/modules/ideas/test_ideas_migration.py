"""Migration ``0010_ideas``: ``ideas.ideas``, its RLS and the ``metis_app`` grants on ``ideas``.

Seam: what an operator sees in Postgres after ``alembic upgrade head`` (catalog,
privileges), plus a replay of the downgrade and upgrade SQL in a rolled-back
transaction (DDL is transactional in Postgres), as the auth migration test does.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from idea_helpers import create, owner
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from tests.helpers.auth import APP_ROLE
from tests.helpers.migrations import load_migration

MIGRATION = "0010_ideas.py"


async def _scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return await conn.scalar(text(sql), params)


async def _replay(conn: AsyncConnection, statements: tuple[str, ...]) -> None:
    for statement in statements:
        await conn.execute(text(statement))


async def test_the_ideas_table_lives_in_the_ideas_schema_with_rls(engine: AsyncEngine) -> None:
    row = await _scalar(
        engine,
        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
        "WHERE oid = 'ideas.ideas'::regclass",
    )

    assert row is True


async def test_metis_app_can_use_the_ideas_tables(engine: AsyncEngine) -> None:
    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        assert await _scalar(
            engine,
            "SELECT has_table_privilege(:role, 'ideas.ideas', :privilege)",
            role=APP_ROLE,
            privilege=privilege,
        ), privilege
    assert await _scalar(
        engine, "SELECT has_schema_privilege(:role, 'ideas', 'USAGE')", role=APP_ROLE
    )


async def test_metis_app_gets_default_privileges_on_tables_added_to_ideas_later(
    engine: AsyncEngine,
) -> None:
    acl = await _scalar(
        engine,
        "SELECT defaclacl::text FROM pg_default_acl d "
        "JOIN pg_namespace n ON n.oid = d.defaclnamespace "
        "WHERE n.nspname = 'ideas' AND d.defaclobjtype = 'r'",
    )

    assert acl is not None
    assert f"{APP_ROLE}=arwd" in acl


@pytest.mark.parametrize(
    "bad_values",
    ["stage = 'archived'", "kind = 'hardware'", "current_score = 101", "current_score = -1"],
)
async def test_the_table_refuses_values_outside_its_check_constraints(
    client: httpx.AsyncClient, engine: AsyncEngine, bad_values: str
) -> None:
    ada = await owner(client, engine)
    created = await create(client, ada)

    async with engine.connect() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(f"UPDATE ideas.ideas SET {bad_values} WHERE id = :id"), {"id": created["id"]}
            )
        await conn.rollback()


async def test_the_downgrade_revokes_access_and_the_upgrade_grants_it_again(
    engine: AsyncEngine,
) -> None:
    migration = load_migration(MIGRATION)
    async with engine.connect() as conn:
        await conn.execute(text("DROP TABLE ideas.ideas CASCADE"))
        await _replay(conn, migration.SCHEMA_DOWN_SQL)
        assert not await conn.scalar(
            text("SELECT has_schema_privilege(:role, 'ideas', 'USAGE')"), {"role": APP_ROLE}
        )
        assert await conn.scalar(text("SELECT to_regnamespace('ideas')")) is not None

        await _replay(conn, migration.SCHEMA_UP_SQL)
        assert await conn.scalar(
            text("SELECT has_schema_privilege(:role, 'ideas', 'USAGE')"), {"role": APP_ROLE}
        )
        await conn.rollback()
