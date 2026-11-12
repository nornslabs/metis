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
    # This function enables RLS on a tenant table with workspace isolation
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enable_tenant_rls(table_name regclass)
        RETURNS void AS $$
        BEGIN
            -- Enable RLS on the table
            EXECUTE 'ALTER TABLE ' || table_name || ' ENABLE ROW LEVEL SECURITY';
            -- Force RLS so superuser bypasses don't leak data
            EXECUTE 'ALTER TABLE ' || table_name || ' FORCE ROW LEVEL SECURITY';
            -- Create policy that filters by workspace_id from session
            EXECUTE 'CREATE POLICY tenant_isolation ON '
                    || table_name
                    || ' FOR ALL USING (workspace_id = '
                    || "current_setting('app.workspace_id')::uuid)";
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    """Drop all schemas (extensions cannot be dropped while in use).

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

        await connection.exec_text(
            """
            CREATE OR REPLACE FUNCTION enable_tenant_rls(table_name regclass)
            RETURNS void AS $$
            BEGIN
                EXECUTE 'ALTER TABLE ' || table_name || ' ENABLE ROW LEVEL SECURITY';
                EXECUTE 'ALTER TABLE ' || table_name || ' FORCE ROW LEVEL SECURITY';
                EXECUTE 'CREATE POLICY tenant_isolation ON '
                        || table_name
                        || ' FOR ALL USING (workspace_id = '
                        || "current_setting('app.workspace_id')::uuid)";
            END;
            $$ LANGUAGE plpgsql;
            """
        )


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