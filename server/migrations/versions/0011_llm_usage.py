"""Migration ``0011_llm_usage``: ``ideas.llm_usage``, one row per completed LLM call.

A tenant table (RLS through ``enable_tenant_rls``); ``metis_app`` gets DML through the
default privileges ``0010_ideas`` set on the ``ideas`` schema. ``run_id`` has no foreign
key: the runs table arrives with SHIP-225, which adds it. ``cost_usd`` is null unless a
price is configured for the model.
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_llm_usage"
down_revision = "0010_ideas"
branch_labels = None
depends_on = None

SCHEMA = "ideas"
TABLE = "llm_usage"
RLS_SQL = f"SELECT enable_tenant_rls('{SCHEMA}.{TABLE}'::regclass)"


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_llm_usage"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["identity.workspaces.id"],
            name="fk_llm_usage_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="ck_llm_usage_tokens"),
        sa.CheckConstraint("cost_usd IS NULL OR cost_usd >= 0", name="ck_llm_usage_cost"),
        schema=SCHEMA,
    )
    op.create_index("ix_llm_usage_workspace_run", TABLE, ["workspace_id", "run_id"], schema=SCHEMA)
    op.execute(RLS_SQL)


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
