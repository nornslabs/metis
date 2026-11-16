"""Migration ``0013_workflow_runs``: ``ideas.workflow_runs``, one row per agent run.

A tenant table (RLS through ``enable_tenant_rls``). ``metis_app`` gets DML through the
default privileges ``0010_ideas`` set on the ``ideas`` schema. ``status`` and ``kind`` are
text + CHECK, like the other enums. ``idempotency_key`` is unique per workspace (Postgres
treats nulls as distinct, so runs without a key never collide).

Also adds the foreign key ``ideas.llm_usage.run_id`` waited for (``0011_llm_usage``), and
``ideas.list_running_runs()``: RLS hides every run until a workspace is set, but crash
recovery must find ``running`` runs across workspaces. The function is ``SECURITY DEFINER``
(it runs as the migration owner, which must be a superuser or ``BYPASSRLS`` role, as the
migrations already assume), returns only ``(run_id, workspace_id)`` and is executable by
``metis_app`` alone.

The downgrade drops the function, the foreign key and the table.
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_workflow_runs"
down_revision = "0012_agent_checkpoints"
branch_labels = None
depends_on = None

APP_ROLE = "metis_app"
SCHEMA = "ideas"
TABLE = "workflow_runs"
USAGE_TABLE = "llm_usage"
USAGE_FK = "fk_llm_usage_run_id_workflow_runs"
STATUSES = ("queued", "running", "awaiting_user", "succeeded", "failed", "cancelled")
KINDS = ("pipeline",)
RLS_SQL = f"SELECT enable_tenant_rls('{SCHEMA}.{TABLE}'::regclass)"
LIST_RUNNING_FUNCTION = f"{SCHEMA}.list_running_runs()"

FUNCTION_UP_SQL: tuple[str, ...] = (
    f"""
    CREATE FUNCTION {LIST_RUNNING_FUNCTION}
    RETURNS TABLE (run_id uuid, workspace_id uuid)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path = {SCHEMA}, pg_catalog
    AS $$ SELECT id, workspace_id FROM {SCHEMA}.{TABLE} WHERE status = 'running' $$
    """,
    f"REVOKE ALL ON FUNCTION {LIST_RUNNING_FUNCTION} FROM PUBLIC",
    f"GRANT EXECUTE ON FUNCTION {LIST_RUNNING_FUNCTION} TO {APP_ROLE}",
)
FUNCTION_DOWN_SQL: tuple[str, ...] = (f"DROP FUNCTION IF EXISTS {LIST_RUNNING_FUNCTION}",)


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idea_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default=sa.text("'pipeline'")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column("pending_interrupt", postgresql.JSONB(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runs"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["identity.workspaces.id"],
            name="fk_workflow_runs_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["idea_id"],
            [f"{SCHEMA}.ideas.id"],
            name="fk_workflow_runs_idea_id_ideas",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id", "idempotency_key", name="uq_workflow_runs_workspace_id_idempotency_key"
        ),
        sa.CheckConstraint(_in_list("status", STATUSES), name="ck_workflow_runs_status"),
        sa.CheckConstraint(_in_list("kind", KINDS), name="ck_workflow_runs_kind"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_workflow_runs_workspace_status", TABLE, ["workspace_id", "status"], schema=SCHEMA
    )
    op.create_index("ix_workflow_runs_idea_id", TABLE, ["idea_id"], schema=SCHEMA)
    op.execute(RLS_SQL)
    op.create_foreign_key(
        USAGE_FK,
        USAGE_TABLE,
        TABLE,
        ["run_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )
    for statement in FUNCTION_UP_SQL:
        op.execute(statement)


def downgrade() -> None:
    for statement in FUNCTION_DOWN_SQL:
        op.execute(statement)
    op.drop_constraint(USAGE_FK, USAGE_TABLE, schema=SCHEMA, type_="foreignkey")
    op.drop_table(TABLE, schema=SCHEMA)
