"""Initial migration: extensions, schemas, and RLS helper.

Creates:
- Extensions: vector (pgvector), pgcrypto (UUID v7 generation)
- Module schemas: identity, ideas, research, scoring, planning,
  integrations, memory, notifications, core (for outbox)
- Helper function enable_tenant_rls() for tenant isolation
"""


from alembic import op
from sqlalchemy import Connection

# alembic version identifier
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


# Enables RLS on a tenant table with workspace isolation. Later migrations call
# ``SELECT enable_tenant_rls('<schema>.<table>'::regclass)``. An unset (NULL) or
# cleared ('') ``app.workspace_id`` matches no rows, so access fails closed.
ENABLE_TENANT_RLS_SQL = """
CREATE OR REPLACE FUNCTION enable_tenant_rls(table_name regclass)
RETURNS void AS $$
BEGIN
    EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', table_name);
    -- FORCE applies the policy to the table owner too (superusers still bypass RLS)
    EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format(
        'CREATE POLICY tenant_isolation ON %s FOR ALL '
        || 'USING (workspace_id = nullif(current_setting(%L, true), %L)::uuid)',
        table_name, 'app.workspace_id', ''
    );
END;
$$ LANGUAGE plpgsql;
"""

DROP_TENANT_RLS_SQL = "DROP FUNCTION IF EXISTS enable_tenant_rls(regclass)"


def upgrade() -> None:
    """Create extensions, schemas, and RLS helper function."""
    # Create extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Create module schemas
    schemas = [
        "core",  # for outbox and shared tables
        "identity",
        "ideas",
        "research",
        "scoring",
        "planning",
        "integrations",
        "memory",
        "notifications",
    ]
    for schema in schemas:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')

    # Create RLS helper function for migrations to use
    op.execute(ENABLE_TENANT_RLS_SQL)


def downgrade() -> None:
    """Drop all schemas and the RLS helper (extensions cannot be dropped while in use).

    Note: Extensions are not dropped to avoid errors if any tables
    reference them. This is safe for development/reset purposes.
    """
    # Drop all schemas and their contents
    schemas = [
        "notifications",
        "memory",
        "integrations",
        "planning",
        "scoring",
        "research",
        "ideas",
        "identity",
        "core",
    ]
    for schema in schemas:
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    op.execute(DROP_TENANT_RLS_SQL)


# -----------------------------------------------------------------------------
# Async version for future async migrations
# -----------------------------------------------------------------------------


async def upgrade_async(connection: Connection) -> None:
    """Async version of upgrade (for future use with AsyncConnection)."""
    await connection.exec_text("SELECT 1")  # keep connection alive

    schemas = [
        "core",
        "identity",
        "ideas",
        "research",
        "scoring",
        "planning",
        "integrations",
        "memory",
        "notifications",
    ]

    async with connection.begin():
        await connection.exec_text("CREATE EXTENSION IF NOT EXISTS vector")
        await connection.exec_text("CREATE EXTENSION IF NOT EXISTS pgcrypto")

        for schema in schemas:
            await connection.exec_text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')

        await connection.exec_text(ENABLE_TENANT_RLS_SQL)


async def downgrade_async(connection: Connection) -> None:
    """Async version of downgrade."""
    schemas = [
        "notifications",
        "memory",
        "integrations",
        "planning",
        "scoring",
        "research",
        "ideas",
        "identity",
        "core",
    ]

    async with connection.begin():
        for schema in schemas:
            await connection.exec_text(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await connection.exec_text(DROP_TENANT_RLS_SQL)