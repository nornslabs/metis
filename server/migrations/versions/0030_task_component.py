"""``planning.tasks.component``: the HLD component a task belongs to.

Set by the Planner for an idea that has an HLD (one of the HLD's component names); the Linear
export writes it in the issue's Design line. Null for a plan of an idea with no HLD and for plans
saved before this change. ``metis_app`` already has UPDATE on tasks (task edits), so no grant
changes.
"""

import sqlalchemy as sa
from alembic import op

revision = "0030_task_component"
down_revision = "0029_spec_hlds"
branch_labels = None
depends_on = None

CHECK = "ck_tasks_component_length"


def upgrade() -> None:
    op.add_column("tasks", sa.Column("component", sa.Text(), nullable=True), schema="planning")
    op.create_check_constraint(
        CHECK, "tasks", "char_length(component) BETWEEN 1 AND 120", schema="planning"
    )


def downgrade() -> None:
    op.drop_constraint(CHECK, "tasks", schema="planning", type_="check")
    op.drop_column("tasks", "component", schema="planning")
