"""Move ``users``, ``sessions`` and ``auth_identities`` from ``identity`` to a new ``auth`` schema.

``ALTER TABLE … SET SCHEMA`` moves each table with its indexes, constraints and
per-table grants, keeping their names; no data is copied. The FKs from
``identity.workspaces`` and ``identity.members`` follow ``users`` because
Postgres tracks FKs by table, not by name.

``metis_app`` gets on ``auth`` what ``0004_app_role`` grants on ``identity``,
including default privileges for tables added later. The constants are copied,
not imported, so this migration stays self-contained.

Downgrade moves the tables back, revokes the grants and drops the schema
(not ``CASCADE``: it fails loudly if anything else landed there).

The SQL lives in module-level constants so a test can replay it.
"""

from alembic import op

revision = "0008_auth_schema"
down_revision = "0007_drop_users_auth_sub"
branch_labels = None
depends_on = None

APP_ROLE = "metis_app"
SOURCE_SCHEMA = "identity"
TARGET_SCHEMA = "auth"
MOVED_TABLES = ("users", "sessions", "auth_identities")
_TABLE_PRIVILEGES = "SELECT, INSERT, UPDATE, DELETE"


def _move(from_schema: str, to_schema: str) -> tuple[str, ...]:
    return tuple(
        f"ALTER TABLE {from_schema}.{table} SET SCHEMA {to_schema}" for table in MOVED_TABLES
    )


UPGRADE_SQL: tuple[str, ...] = (
    f"CREATE SCHEMA {TARGET_SCHEMA}",
    *_move(SOURCE_SCHEMA, TARGET_SCHEMA),
    f"GRANT USAGE ON SCHEMA {TARGET_SCHEMA} TO {APP_ROLE}",
    f"GRANT {_TABLE_PRIVILEGES} ON ALL TABLES IN SCHEMA {TARGET_SCHEMA} TO {APP_ROLE}",
    f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {TARGET_SCHEMA} TO {APP_ROLE}",
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA {TARGET_SCHEMA} "
    f"GRANT {_TABLE_PRIVILEGES} ON TABLES TO {APP_ROLE}",
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA {TARGET_SCHEMA} "
    f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}",
)

DOWNGRADE_SQL: tuple[str, ...] = (
    *_move(TARGET_SCHEMA, SOURCE_SCHEMA),
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA {TARGET_SCHEMA} "
    f"REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}",
    f"ALTER DEFAULT PRIVILEGES IN SCHEMA {TARGET_SCHEMA} "
    f"REVOKE {_TABLE_PRIVILEGES} ON TABLES FROM {APP_ROLE}",
    f"REVOKE USAGE ON SCHEMA {TARGET_SCHEMA} FROM {APP_ROLE}",
    f"DROP SCHEMA {TARGET_SCHEMA}",
)


def upgrade() -> None:
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_SQL:
        op.execute(statement)
