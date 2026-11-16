"""``ideas.ideas``: a user's idea and its stage, and ``metis_app`` access to the ``ideas`` schema.

The schema itself is created by ``0001_initial`` (which also drops it on downgrade).

``kind`` and ``stage`` are text + CHECK (like ``members.role``). ``archived_at`` is
the soft archive: archived ideas are hidden by the module. ``current_score`` is
written only by the scoring module. The table is a tenant table (RLS through
``enable_tenant_rls``).

``metis_app`` gets on ``ideas`` what ``0008_auth_schema`` gives it on ``auth``,
with default privileges for tables added later. The constants are copied, not
imported, so the migration stays self-contained. The downgrade drops the table and
revokes the grants; the empty schema stays, as ``0001_initial`` owns it. SQL lives in
module-level constants so a test can replay it.
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_ideas"
down_revision = "0009_rename_auth_identities"
branch_labels = None
depends_on = None

APP_ROLE = "metis_app"
SCHEMA = "ideas"
TABLE = "ideas"
STAGES = (
    "intake",
    "interviewing",
    "researching",
    "scoring",
    "advising",
    "spec_draft",
    "spec_confirmed",
    "planning",
    "exported",
)
KINDS = ("software", "other")
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
RLS_SQL = f"SELECT enable_tenant_rls('{SCHEMA}.{TABLE}'::regclass)"


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    for statement in SCHEMA_UP_SQL:
        op.execute(statement)
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=True),
        sa.Column("stage", sa.Text(), nullable=False, server_default=sa.text("'intake'")),
        sa.Column("current_score", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_ideas"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["identity.workspaces.id"],
            name="fk_ideas_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["auth.users.id"], name="fk_ideas_created_by_users"
        ),
        sa.CheckConstraint(_in_list("stage", STAGES), name="ck_ideas_stage"),
        sa.CheckConstraint(f"kind IS NULL OR {_in_list('kind', KINDS)}", name="ck_ideas_kind"),
        sa.CheckConstraint(
            "current_score IS NULL OR current_score BETWEEN 0 AND 100",
            name="ck_ideas_current_score",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_ideas_workspace_list",
        TABLE,
        ["workspace_id", sa.text("created_at DESC"), sa.text("id DESC")],
        schema=SCHEMA,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.execute(RLS_SQL)


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
    for statement in SCHEMA_DOWN_SQL:
        op.execute(statement)
