"""Migration ``0020_spec_versions``: the idea's spec, one immutable row per version.

Table ``ideas.spec_versions``: the text of one version of an idea's spec (markdown and its
parsed sections), numbered per idea from 1, written by the Architect (``agent``) or a member
(``user``). Tenant table with RLS. ``metis_app`` gets ``SELECT`` and ``INSERT`` only, so a
version cannot be changed or deleted through the app role. One agent draft per workflow run
(partial unique index) keeps a crash re-run from drafting twice.

Column ``ideas.ideas.confirmed_spec_version_id``: the version the user confirmed (null until
then). The downgrade drops the column and the table.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_spec_versions"
down_revision = "3aaa8e5afd8c"
branch_labels = None
depends_on = None

APP_ROLE = "metis_app"
SCHEMA = "ideas"
TABLE = "spec_versions"
SOURCES = ("agent", "user")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid(name: str, *, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    op.create_table(
        TABLE,
        _uuid("id"),
        _uuid("workspace_id"),
        _uuid("idea_id"),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("sections", postgresql.JSONB(), nullable=False),
        _uuid("run_id", nullable=True),
        _uuid("created_by", nullable=True),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name=f"pk_{TABLE}"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["identity.workspaces.id"],
            name=f"fk_{TABLE}_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["idea_id"],
            [f"{SCHEMA}.ideas.id"],
            name=f"fk_{TABLE}_idea_id_ideas",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{SCHEMA}.workflow_runs.id"],
            name=f"fk_{TABLE}_run_id_workflow_runs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["auth.users.id"], name=f"fk_{TABLE}_created_by_users"
        ),
        sa.CheckConstraint("number >= 1", name=f"ck_{TABLE}_number"),
        sa.CheckConstraint(_in_list("source", SOURCES), name=f"ck_{TABLE}_source"),
        sa.CheckConstraint("jsonb_typeof(sections) = 'object'", name=f"ck_{TABLE}_sections"),
        sa.UniqueConstraint("idea_id", "number", name=f"uq_{TABLE}_idea_number"),
        schema=SCHEMA,
    )
    op.create_index(
        f"ix_{TABLE}_workspace_idea",
        TABLE,
        ["workspace_id", "idea_id", sa.text("number DESC")],
        schema=SCHEMA,
    )
    op.create_index(
        f"uq_{TABLE}_agent_run",
        TABLE,
        ["run_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("source = 'agent'"),
    )
    op.execute(f"SELECT enable_tenant_rls('{SCHEMA}.{TABLE}'::regclass)")
    op.execute(f"REVOKE ALL ON {SCHEMA}.{TABLE} FROM {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON {SCHEMA}.{TABLE} TO {APP_ROLE}")

    op.add_column(
        "ideas",
        _uuid("confirmed_spec_version_id", nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_ideas_confirmed_spec_version_id_spec_versions",
        "ideas",
        TABLE,
        ["confirmed_spec_version_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_ideas_confirmed_spec_version_id_spec_versions",
        "ideas",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_column("ideas", "confirmed_spec_version_id", schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
