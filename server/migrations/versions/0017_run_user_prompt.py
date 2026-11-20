"""Persist continuation prompts on workflow runs."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_run_user_prompt"
down_revision = "0016_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column("user_prompt", sa.Text(), nullable=True),
        schema="ideas",
    )


def downgrade() -> None:
    op.drop_column("workflow_runs", "user_prompt", schema="ideas")
