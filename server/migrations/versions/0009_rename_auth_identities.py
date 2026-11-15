"""Rename ``auth.auth_identities`` to ``auth.identities``.

The ``auth_`` prefix dates from ``0006``, when the table lived in the
``identity`` schema; ``0008`` moved it to ``auth``, where the prefix only
repeats the schema. Renames the table, its constraints and its index; no data
is copied and grants follow the table. Renaming a primary key or unique
constraint also renames its backing index.

The SQL lives in module-level constants so a test can replay it.
"""

from alembic import op

revision = "0009_rename_auth_identities"
down_revision = "0008_auth_schema"
branch_labels = None
depends_on = None

SCHEMA = "auth"
OLD_TABLE = "auth_identities"
NEW_TABLE = "identities"
CONSTRAINT_SUFFIXES = ("pk_{}", "fk_{}_user_id_users", "uq_{}_provider_subject", "ck_{}_provider")
INDEX = "ix_{}_user_id"


def _rename(old: str, new: str) -> tuple[str, ...]:
    return (
        f"ALTER TABLE {SCHEMA}.{old} RENAME TO {new}",
        *(
            f"ALTER TABLE {SCHEMA}.{new} RENAME CONSTRAINT {c.format(old)} TO {c.format(new)}"
            for c in CONSTRAINT_SUFFIXES
        ),
        f"ALTER INDEX {SCHEMA}.{INDEX.format(old)} RENAME TO {INDEX.format(new)}",
    )


UPGRADE_SQL: tuple[str, ...] = _rename(OLD_TABLE, NEW_TABLE)
DOWNGRADE_SQL: tuple[str, ...] = _rename(NEW_TABLE, OLD_TABLE)


def upgrade() -> None:
    for statement in UPGRADE_SQL:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_SQL:
        op.execute(statement)
