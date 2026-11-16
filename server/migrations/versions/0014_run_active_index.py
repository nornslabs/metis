"""Migration ``0014_run_active_index``: one active run per idea.

A partial unique index on ``ideas.workflow_runs (idea_id)`` for runs that are ``queued``,
``running`` or ``awaiting_user``. The runs API checks first and answers ``409`` itself; the
index makes the rule hold when two starts race.

The downgrade drops the index.
"""

from alembic import op

revision = "0014_run_active_index"
down_revision = "0013_workflow_runs"
branch_labels = None
depends_on = None

SCHEMA = "ideas"
TABLE = "workflow_runs"
INDEX = "uq_workflow_runs_active_idea"
ACTIVE_STATUSES = ("queued", "running", "awaiting_user")
ACTIVE_PREDICATE = f"status IN ({', '.join(repr(s) for s in ACTIVE_STATUSES)})"


def upgrade() -> None:
    op.create_index(
        INDEX,
        TABLE,
        ["idea_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=ACTIVE_PREDICATE,
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE, schema=SCHEMA)
