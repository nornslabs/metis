"""Migration ``0026_export_partial``: an export can end ``partial``.

``integrations.export_jobs.status`` gains ``partial`` (some Linear items were saved and some
failed). The downgrade turns ``partial`` rows into ``failed`` before it restores the old CHECK.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_export_partial"
down_revision = "957fe3c9e5f8"
branch_labels = None
depends_on = None

SCHEMA = "integrations"
TABLE = "export_jobs"
CONSTRAINT = "ck_export_jobs_status"
OLD = "'approved', 'declined', 'running', 'succeeded', 'failed'"
NEW = "'approved', 'declined', 'running', 'succeeded', 'partial', 'failed'"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="check")
    op.create_check_constraint(CONSTRAINT, TABLE, sa.text(f"status IN ({NEW})"), schema=SCHEMA)


def downgrade() -> None:
    op.execute(
        sa.text(f"UPDATE {SCHEMA}.{TABLE} SET status = 'failed' WHERE status = 'partial'")
    )
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="check")
    op.create_check_constraint(CONSTRAINT, TABLE, sa.text(f"status IN ({OLD})"), schema=SCHEMA)
