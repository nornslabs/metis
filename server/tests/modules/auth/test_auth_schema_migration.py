"""Migrations ``0008_auth_schema`` and ``0009_rename_auth_identities``: ``auth.users``,
``auth.sessions`` and ``auth.identities``.

Seam: what an operator can see in Postgres after ``alembic upgrade head`` (the
catalog, privileges, cascades), plus a replay of the migration's SQL in a
rolled-back transaction (DDL is transactional in Postgres), as the prior art
``test_downgrade_restores_auth_sub_from_google_identities`` does.
"""

from __future__ import annotations

from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from metis.modules.auth import service as auth_service
from tests.helpers.auth import APP_ROLE, auth, sign_in
from tests.helpers.migrations import load_migration

# Names at head (after 0009) and as 0008 moved them (before 0009).
AUTH_TABLES = ("users", "sessions", "identities")
MOVED_TABLES = ("users", "sessions", "auth_identities")
IDENTITY_CONSTRAINTS = (
    "pk_identities",
    "fk_identities_user_id_users",
    "uq_identities_provider_subject",
    "ck_identities_provider",
)
USER_FKS = ("fk_workspaces_created_by_users", "fk_members_user_id_users")


async def _schemas_of(
    conn: AsyncConnection, names: tuple[str, ...] = AUTH_TABLES
) -> dict[str, str]:
    rows = await conn.execute(
        text(
            "SELECT c.relname, n.nspname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relkind = 'r' AND c.relname = ANY(:names) "
            "AND n.nspname IN ('auth', 'identity')"
        ),
        {"names": list(names)},
    )
    return dict(rows.all())


async def _replay(conn: AsyncConnection, statements: tuple[str, ...]) -> None:
    for statement in statements:
        await conn.execute(text(statement))


async def _scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return await conn.scalar(text(sql), params)


async def test_auth_tables_live_in_the_auth_schema(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        assert await _schemas_of(conn) == dict.fromkeys(AUTH_TABLES, "auth")
        assert await _schemas_of(conn, ("auth_identities",)) == {}


async def test_workspace_and_member_fks_reference_auth_users(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT conname, confrelid::regclass::text FROM pg_constraint "
                "WHERE conname = ANY(:names)"
            ),
            {"names": list(USER_FKS)},
        )
        assert dict(rows.all()) == dict.fromkeys(USER_FKS, "auth.users")


async def test_deleting_a_user_cascades_to_sessions_identities_and_members(
    engine: AsyncEngine, client: httpx.AsyncClient
) -> None:
    token = await sign_in(engine)
    assert (await client.get("/v1/me", headers=auth(token))).status_code == 200

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM identity.workspaces"))
        await conn.execute(text("DELETE FROM auth.users"))

    for table in ("auth.sessions", "auth.identities", "identity.members"):
        assert await _scalar(engine, f"SELECT count(*) FROM {table}") == 0


async def test_app_role_has_dml_and_default_privileges_on_auth(engine: AsyncEngine) -> None:
    for table in AUTH_TABLES:
        allowed = await _scalar(
            engine,
            "SELECT has_table_privilege(:role, :table, 'SELECT, INSERT, UPDATE, DELETE')",
            role=APP_ROLE,
            table=f"auth.{table}",
        )
        assert allowed, table
    defaults = await _scalar(
        engine,
        "SELECT array_agg(d.defaclobjtype::text ORDER BY d.defaclobjtype) "
        "FROM pg_default_acl d JOIN pg_namespace n ON n.oid = d.defaclnamespace "
        "WHERE n.nspname = 'auth' AND d.defaclacl::text LIKE '%' || :role || '=%'",
        role=APP_ROLE,
    )
    assert defaults == ["S", "r"]


async def test_downgrade_and_upgrade_move_the_tables_and_keep_sessions_resolving(
    engine: AsyncEngine, redis: Redis
) -> None:
    migration = load_migration("0008_auth_schema.py")
    rename = load_migration("0009_rename_auth_identities.py")
    token = await sign_in(engine)

    async with engine.connect() as conn, conn.begin() as tx:
        auth_oid = await conn.scalar(text("SELECT to_regnamespace('auth')::oid"))
        default_acls_sql = text("SELECT count(*) FROM pg_default_acl WHERE defaclnamespace = :oid")
        default_acls_before = await conn.scalar(default_acls_sql, {"oid": auth_oid})
        await _replay(conn, rename.DOWNGRADE_SQL)
        await _replay(conn, migration.DOWNGRADE_SQL)
        after_downgrade = await _schemas_of(conn, MOVED_TABLES)
        auth_schema = await conn.scalar(text("SELECT to_regnamespace('auth') IS NOT NULL"))
        default_acls_after = await conn.scalar(default_acls_sql, {"oid": auth_oid})
        await _replay(conn, migration.UPGRADE_SQL)
        await _replay(conn, rename.UPGRADE_SQL)
        after_upgrade = await _schemas_of(conn)
        await redis.flushdb()  # the lookup must hit the moved table, not the cache
        async with AsyncSession(bind=conn) as session:
            active = await auth_service.resolve_session(session, redis, token)
            user = await auth_service.get_session_user(session, active)
        await tx.rollback()

    assert after_downgrade == dict.fromkeys(MOVED_TABLES, "identity")
    assert auth_schema is False
    assert default_acls_before > 0
    assert default_acls_after == 0
    assert after_upgrade == dict.fromkeys(AUTH_TABLES, "auth")
    assert user.user.email == "ada@example.com"


async def test_identities_constraints_and_index_carry_the_new_name(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        constraints = await conn.execute(
            text("SELECT conname FROM pg_constraint WHERE conrelid = 'auth.identities'::regclass")
        )
        indexes = await conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'auth' AND tablename = 'identities'"
            )
        )
    assert set(constraints.scalars()) == set(IDENTITY_CONSTRAINTS)
    assert set(indexes.scalars()) == {
        "pk_identities",
        "uq_identities_provider_subject",
        "ix_identities_user_id",
    }


async def test_rename_downgrade_restores_the_old_names(engine: AsyncEngine) -> None:
    rename = load_migration("0009_rename_auth_identities.py")

    async with engine.connect() as conn, conn.begin() as tx:
        await _replay(conn, rename.DOWNGRADE_SQL)
        old = await conn.scalar(text("SELECT to_regclass('auth.auth_identities') IS NOT NULL"))
        old_index = await conn.scalar(
            text("SELECT to_regclass('auth.ix_auth_identities_user_id') IS NOT NULL")
        )
        new = await conn.scalar(text("SELECT to_regclass('auth.identities') IS NOT NULL"))
        await tx.rollback()

    assert old is True
    assert old_index is True
    assert new is False
