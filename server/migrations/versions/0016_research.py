"""Migration ``0016_research``: research snapshots, sourced items and the competitor KB.

Tables in the ``research`` schema (created by ``0001_initial``), all tenant tables with RLS
through ``enable_tenant_rls``:

- ``snapshots``: one research version of an idea, written by one run. ``closed_at`` is null
  while the run still adds items; a closed snapshot is immutable. A partial unique index
  allows one open snapshot per run, so a node that re-runs cannot open a second one.
- ``items``: sourced findings of a snapshot. ``competitor`` and ``market_fact`` need a
  ``url`` (CHECK); ``confidence`` is 0–1.
- ``competitors``: the workspace's competitor knowledge base, deduped on the normalized
  ``domain`` (unique per workspace). ``embedding`` is a 1536-dimension pgvector column
  (null when the provider has no embeddings) with an HNSW cosine index.
- ``idea_competitors``: which competitors a snapshot found for its idea, with ``overlap`` 0–1.

``metis_app`` gets on ``research`` what ``0010_ideas`` gives it on ``ideas``. The downgrade
drops the tables and revokes the grants; the empty schema stays, as ``0001_initial`` owns it.
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0016_research"
down_revision = "0015_interview_turns"
branch_labels = None
depends_on = None

APP_ROLE = "metis_app"
SCHEMA = "research"
WORKSPACES = "identity.workspaces.id"
EMBEDDING_DIMENSIONS = 1536
ITEM_KINDS = ("competitor", "market_fact", "trend", "risk")
SOURCED_KINDS = ("competitor", "market_fact")
OPEN_SNAPSHOT_INDEX = "uq_snapshots_open_run"
HNSW_INDEX = "ix_competitors_embedding_hnsw"
TABLES = ("snapshots", "items", "competitors", "idea_competitors")

_TABLE_PRIVILEGES = "SELECT, INSERT, UPDATE, DELETE"
SCHEMA_UP_SQL: tuple[str, ...] = (
    f"GRANT USAGE ON SCHEMA {SCHEMA} TO {APP_ROLE}",
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} "
    f"GRANT {_TABLE_PRIVILEGES} ON TABLES TO {APP_ROLE}",
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}",
)
SCHEMA_DOWN_SQL: tuple[str, ...] = (
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} "
    f"REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}",
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} "
    f"REVOKE {_TABLE_PRIVILEGES} ON TABLES FROM {APP_ROLE}",
    f"REVOKE USAGE ON SCHEMA {SCHEMA} FROM {APP_ROLE}",
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid(name: str, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def _fraction(name: str, table: str) -> tuple[sa.Column[object], sa.CheckConstraint]:
    column = sa.Column(name, sa.Numeric(3, 2), nullable=False)
    return column, sa.CheckConstraint(f"{name} BETWEEN 0 AND 1", name=f"ck_{table}_{name}")


def _fk(column: str, target: str, table: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [target], name=f"fk_{table}_{column}_{name}", ondelete="CASCADE"
    )


def upgrade() -> None:
    for statement in SCHEMA_UP_SQL:
        op.execute(statement)
    _create_snapshots()
    _create_items()
    _create_competitors()
    _create_idea_competitors()
    for table in TABLES:
        op.execute(f"SELECT enable_tenant_rls('{SCHEMA}.{table}'::regclass)")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table, schema=SCHEMA)
    for statement in SCHEMA_DOWN_SQL:
        op.execute(statement)


def _create_snapshots() -> None:
    op.create_table(
        "snapshots",
        _uuid("id"),
        _uuid("workspace_id"),
        _uuid("idea_id"),
        _uuid("run_id"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_snapshots"),
        _fk("workspace_id", WORKSPACES, "snapshots", "workspaces"),
        _fk("idea_id", "ideas.ideas.id", "snapshots", "ideas"),
        _fk("run_id", "ideas.workflow_runs.id", "snapshots", "workflow_runs"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_snapshots_workspace_idea_closed",
        "snapshots",
        ["workspace_id", "idea_id", sa.text("closed_at DESC")],
        schema=SCHEMA,
    )
    op.create_index(
        OPEN_SNAPSHOT_INDEX,
        "snapshots",
        ["run_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("closed_at IS NULL"),
    )


def _create_items() -> None:
    confidence, confidence_check = _fraction("confidence", "items")
    op.create_table(
        "items",
        _uuid("id"),
        _uuid("workspace_id"),
        _uuid("snapshot_id"),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("claim", sa.Text(), nullable=False),
        confidence,
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_items"),
        _fk("workspace_id", WORKSPACES, "items", "workspaces"),
        _fk("snapshot_id", f"{SCHEMA}.snapshots.id", "items", "snapshots"),
        sa.CheckConstraint(_in_list("kind", ITEM_KINDS), name="ck_items_kind"),
        sa.CheckConstraint(
            f"url IS NOT NULL OR NOT ({_in_list('kind', SOURCED_KINDS)})",
            name="ck_items_source_url",
        ),
        confidence_check,
        schema=SCHEMA,
    )
    op.create_index("ix_items_snapshot_id", "items", ["snapshot_id", "id"], schema=SCHEMA)


def _create_competitors() -> None:
    op.create_table(
        "competitors",
        _uuid("id"),
        _uuid("workspace_id"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("pricing", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_competitors"),
        _fk("workspace_id", WORKSPACES, "competitors", "workspaces"),
        sa.UniqueConstraint("workspace_id", "domain", name="uq_competitors_workspace_domain"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_competitors_workspace_name",
        "competitors",
        ["workspace_id", sa.text("lower(name)")],
        schema=SCHEMA,
    )
    op.create_index(
        HNSW_INDEX,
        "competitors",
        ["embedding"],
        schema=SCHEMA,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def _create_idea_competitors() -> None:
    overlap, overlap_check = _fraction("overlap", "idea_competitors")
    op.create_table(
        "idea_competitors",
        _uuid("workspace_id"),
        _uuid("idea_id"),
        _uuid("competitor_id"),
        _uuid("snapshot_id"),
        overlap,
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("snapshot_id", "competitor_id", name="pk_idea_competitors"),
        _fk("workspace_id", WORKSPACES, "idea_competitors", "workspaces"),
        _fk("idea_id", "ideas.ideas.id", "idea_competitors", "ideas"),
        _fk("competitor_id", f"{SCHEMA}.competitors.id", "idea_competitors", "competitors"),
        _fk("snapshot_id", f"{SCHEMA}.snapshots.id", "idea_competitors", "snapshots"),
        overlap_check,
        schema=SCHEMA,
    )
    op.create_index(
        "ix_idea_competitors_workspace_idea",
        "idea_competitors",
        ["workspace_id", "idea_id"],
        schema=SCHEMA,
    )
