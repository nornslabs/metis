"""Migration ``0012_agent_checkpoints``: the ``agent`` schema for LangGraph checkpoints.

``AsyncPostgresSaver.setup()`` creates and migrates its own tables, so this migration only
creates the schema and lets ``metis_app`` (the role workers connect as) create and use tables
in it: since Postgres 15 no role but the owner may create tables in ``public``. The checkpoint
tables have no RLS: a thread id is a run id and only workers read them. The downgrade drops
the schema with whatever the library created in it.
"""

from alembic import op

revision = "0012_agent_checkpoints"
down_revision = "0011_llm_usage"
branch_labels = None
depends_on = None

APP_ROLE = "metis_app"
SCHEMA = "agent"

SCHEMA_UP_SQL: tuple[str, ...] = (
    f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}",
    f"GRANT USAGE, CREATE ON SCHEMA {SCHEMA} TO {APP_ROLE}",
    # Tables created by the owner (a deploy that runs ``setup()`` as the migration role)
    # stay usable by the workers.
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} GRANT ALL ON TABLES TO {APP_ROLE}",
)
SCHEMA_DOWN_SQL: tuple[str, ...] = (f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE",)


def upgrade() -> None:
    for statement in SCHEMA_UP_SQL:
        op.execute(statement)


def downgrade() -> None:
    for statement in SCHEMA_DOWN_SQL:
        op.execute(statement)
