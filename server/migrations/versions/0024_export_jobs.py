"""Migration ``0024_export_jobs``: the record of each export's approval decision.

``integrations.export_jobs``: one row per run that reached the export approval. It stores the
preview the user saw (``summary``), who decided and when (``decided_by``, ``decided_at``) and
the outcome (``status``). ``run_id`` is unique, so a resumed or re-run approval never adds a
second row. Later steps move ``approved`` to ``running``, ``succeeded`` or ``failed`` and set
``finished_at``.

A tenant table (RLS); ``metis_app`` gets SELECT, INSERT and UPDATE (a decision is never
deleted). The downgrade drops the table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024_export_jobs"
down_revision = "0023_integrations"
branch_labels = None
depends_on = None

APP_ROLE = "metis_app"
SCHEMA = "integrations"
TABLE = "export_jobs"
STATUSES = ("approved", "declined", "running", "succeeded", "failed")


def _uuid(name: str, *, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        TABLE,
        _uuid("id"),
        _uuid("workspace_id"),
        _uuid("idea_id"),
        _uuid("plan_id"),
        _uuid("run_id"),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
        _uuid("decided_by"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_export_jobs"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["identity.workspaces.id"],
            name="fk_export_jobs_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["idea_id"],
            ["ideas.ideas.id"],
            name="fk_export_jobs_idea_id_ideas",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["planning.plans.id"],
            name="fk_export_jobs_plan_id_plans",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ideas.workflow_runs.id"],
            name="fk_export_jobs_run_id_workflow_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["auth.users.id"], name="fk_export_jobs_decided_by_users"
        ),
        sa.CheckConstraint("provider IN ('linear')", name="ck_export_jobs_provider"),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(v) for v in STATUSES)})", name="ck_export_jobs_status"
        ),
        sa.UniqueConstraint("run_id", name="uq_export_jobs_run"),
        schema=SCHEMA,
    )
    op.create_index("ix_export_jobs_idea", TABLE, ["workspace_id", "idea_id"], schema=SCHEMA)
    op.execute(f"SELECT enable_tenant_rls('{SCHEMA}.{TABLE}'::regclass)")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {SCHEMA}.{TABLE} TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
