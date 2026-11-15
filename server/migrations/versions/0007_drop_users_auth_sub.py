"""Drop ``identity.users.auth_sub``.

Sign-in identity lives in ``identity.auth_identities`` (backfilled from
``auth_sub`` in ``0006_auth_sessions``), and the API no longer accepts the
Auth.js API token whose ``sub`` this column held.

Downgrade restores the column from each user's ``google`` identity. A user with
no Google identity gets ``user:<id>`` so the column can be NOT NULL and unique
again.
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_drop_users_auth_sub"
down_revision = "0006_auth_sessions"
branch_labels = None
depends_on = None

SCHEMA = "identity"
UNIQUE_NAME = "uq_users_auth_sub"

RESTORE_SQL = """
UPDATE identity.users AS u
SET auth_sub = coalesce(
    (
        SELECT i.subject
        FROM identity.auth_identities AS i
        WHERE i.user_id = u.id AND i.provider = 'google'
        ORDER BY i.created_at
        LIMIT 1
    ),
    'user:' || u.id::text
)
"""


def upgrade() -> None:
    op.drop_constraint(UNIQUE_NAME, "users", schema=SCHEMA, type_="unique")
    op.drop_column("users", "auth_sub", schema=SCHEMA)


def downgrade() -> None:
    op.add_column("users", sa.Column("auth_sub", sa.Text(), nullable=True), schema=SCHEMA)
    op.execute(RESTORE_SQL)
    op.alter_column("users", "auth_sub", nullable=False, schema=SCHEMA)
    op.create_unique_constraint(UNIQUE_NAME, "users", ["auth_sub"], schema=SCHEMA)
