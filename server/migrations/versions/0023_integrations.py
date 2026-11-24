"""Migration ``0023_integrations``: MCP connections and external references.

Tables in the ``integrations`` schema (created by ``0001_initial``):

- ``mcp_connections``: one OAuth connection per workspace and provider. The tokens and the
  registered OAuth client are sealed (envelope encryption) in ``sealed_tokens``; a revoked
  connection keeps its row with the tokens wiped, so reconnecting updates it.
- ``external_refs``: a Metis record's id in an external tool (nothing writes it yet).

Both are tenant tables (RLS). ``metis_app`` gets the four DML grants. The downgrade drops the
tables and revokes the grants; the empty schema stays, as ``0001_initial`` owns it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from datetime import datetime

revision = "0023_integrations"
down_revision = "0022_ideas_activity_index"
branch_labels = None
depends_on = None

APP_ROLE = "metis_app"
SCHEMA = "integrations"
PROVIDERS = ("linear", "notion")
STATUSES = ("connected", "expired", "revoked")
TABLES = ("mcp_connections", "external_refs")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid(name: str, *, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    op.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {APP_ROLE}")
    _create_mcp_connections()
    _create_external_refs()
    for table in TABLES:
        op.execute(f"SELECT enable_tenant_rls('{SCHEMA}.{table}'::regclass)")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.{table} TO {APP_ROLE}")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table, schema=SCHEMA)
    op.execute(f"REVOKE USAGE ON SCHEMA {SCHEMA} FROM {APP_ROLE}")


def _create_mcp_connections() -> None:
    op.create_table(
        "mcp_connections",
        _uuid("id"),
        _uuid("workspace_id"),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("server_url", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("sealed_tokens", postgresql.JSONB(), nullable=True),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        _uuid("created_by"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        _timestamp("connected_at"),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_mcp_connections"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["identity.workspaces.id"],
            name="fk_mcp_connections_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["auth.users.id"], name="fk_mcp_connections_created_by_users"
        ),
        sa.CheckConstraint(_in_list("provider", PROVIDERS), name="ck_mcp_connections_provider"),
        sa.CheckConstraint(_in_list("status", STATUSES), name="ck_mcp_connections_status"),
        sa.CheckConstraint("version >= 1", name="ck_mcp_connections_version"),
        sa.CheckConstraint(
            "(status = 'revoked') = (sealed_tokens IS NULL)",
            name="ck_mcp_connections_tokens_revoked",
        ),
        sa.UniqueConstraint(
            "workspace_id", "provider", name="uq_mcp_connections_workspace_provider"
        ),
        schema=SCHEMA,
    )


def _create_external_refs() -> None:
    op.create_table(
        "external_refs",
        _uuid("id"),
        _uuid("workspace_id"),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("local_kind", sa.Text(), nullable=False),
        _uuid("local_id"),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("external_url", sa.Text(), nullable=True),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_external_refs"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["identity.workspaces.id"],
            name="fk_external_refs_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(_in_list("provider", PROVIDERS), name="ck_external_refs_provider"),
        sa.UniqueConstraint(
            "workspace_id",
            "provider",
            "local_kind",
            "local_id",
            name="uq_external_refs_local",
        ),
        schema=SCHEMA,
    )
