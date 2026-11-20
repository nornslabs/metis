"""Add manual rescore and market re-check workflow run kinds."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_manual_refresh_runs"
down_revision = "0017_run_user_prompt"
branch_labels = None
depends_on = None

SCHEMA = "ideas"
TABLE = "workflow_runs"
CONSTRAINT = "ck_workflow_runs_kind"
KINDS = "'pipeline', 'rescore', 'market_recheck'"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="check")
    op.create_check_constraint(
        CONSTRAINT, TABLE, sa.text(f"kind IN ({KINDS})"), schema=SCHEMA
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE ideas.workflow_runs SET kind = 'pipeline' "
            "WHERE kind IN ('rescore', 'market_recheck')"
        )
    )
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="check")
    op.create_check_constraint(
        CONSTRAINT, TABLE, sa.text("kind = 'pipeline'"), schema=SCHEMA
    )
