"""Migration ``0025_workspace_linear_team``: the workspace's Linear team for exports.

Adds ``identity.workspace_settings.linear_team_id`` (text, null): the team the user chose the
first time an export asked. Null means none chosen yet. Backward compatible: the column is
nullable and old code ignores it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_workspace_linear_team"
down_revision = "0024_export_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_settings",
        sa.Column("linear_team_id", sa.Text(), nullable=True),
        schema="identity",
    )


def downgrade() -> None:
    op.drop_column("workspace_settings", "linear_team_id", schema="identity")
