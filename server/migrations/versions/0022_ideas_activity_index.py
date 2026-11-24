"""Migration ``0022_ideas_activity_index``: an index for the ideas list by last activity.

``GET /v1/ideas`` orders and pages by ``(updated_at, id)`` (last activity), so the list needs
an index in that order next to ``ix_ideas_workspace_list`` (created-at order, kept: other code
may still use it). Backward-compatible: no data or column changes. The downgrade drops it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_ideas_activity_index"
down_revision = "0021_planning"
branch_labels = None
depends_on = None

SCHEMA = "ideas"
TABLE = "ideas"
INDEX = "ix_ideas_workspace_activity"


def upgrade() -> None:
    op.create_index(
        INDEX,
        TABLE,
        ["workspace_id", sa.text("updated_at DESC"), sa.text("id DESC")],
        schema=SCHEMA,
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE, schema=SCHEMA)
