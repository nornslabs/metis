"""``ideas.ideas.project_name``: the Linear project name the user approved for the export.

Null until the user approves an export; a re-export reuses it. Linear refuses a project name
over 80 characters, so the column checks the same limit. Existing rows stay null.
"""

import sqlalchemy as sa
from alembic import op

revision = "0028_idea_project_name"
down_revision = "0027_running_runs_updated_at"
branch_labels = None
depends_on = None

CHECK = "ck_ideas_project_name_length"


def upgrade() -> None:
    op.add_column("ideas", sa.Column("project_name", sa.Text(), nullable=True), schema="ideas")
    op.create_check_constraint(
        CHECK, "ideas", "char_length(project_name) BETWEEN 1 AND 80", schema="ideas"
    )


def downgrade() -> None:
    op.drop_constraint(CHECK, "ideas", schema="ideas", type_="check")
    op.drop_column("ideas", "project_name", schema="ideas")
