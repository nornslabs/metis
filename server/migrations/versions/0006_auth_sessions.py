"""Server-side sessions and auth identities in ``identity``.

``auth_identities`` links a user to ``(provider, subject)`` pairs (``google``
now, ``email`` later). ``sessions`` holds one row per signed-in browser; only
the SHA-256 hash of the session token is stored. Neither is a tenant table: no
RLS, and only the identity module reads them. ``metis_app`` gets DML through
the default privileges from ``0004_app_role``.

Every existing user is backfilled with a ``google`` identity from
``users.auth_sub`` (Auth.js Google was the only sign-in path).
``users.auth_sub`` stays until SHIP-267.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_auth_sessions"
down_revision = "0005_provider_keys"
branch_labels = None
depends_on = None

SCHEMA = "identity"

BACKFILL_SQL = """
INSERT INTO identity.auth_identities
    (id, user_id, provider, subject, email, email_verified, created_at)
SELECT gen_random_uuid(), u.id, 'google', u.auth_sub, u.email, true, u.created_at
FROM identity.users AS u
ON CONFLICT (provider, subject) DO NOTHING
"""


def _timestamp(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def _user_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["user_id"],
        ["identity.users.id"],
        name=f"fk_{table}_user_id_users",
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "auth_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        _timestamp("created_at"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_auth_identities"),
        _user_fk("auth_identities"),
        sa.UniqueConstraint(
            "provider", "subject", name="uq_auth_identities_provider_subject"
        ),
        sa.CheckConstraint(
            "provider IN ('google', 'email')", name="ck_auth_identities_provider"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_auth_identities_user_id", "auth_identities", ["user_id"], schema=SCHEMA
    )
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", postgresql.BYTEA(), nullable=False),
        _timestamp("created_at"),
        _timestamp("last_seen_at"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        _user_fk("sessions"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        schema=SCHEMA,
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], schema=SCHEMA)
    op.execute(BACKFILL_SQL)


def downgrade() -> None:
    op.drop_table("sessions", schema=SCHEMA)
    op.drop_table("auth_identities", schema=SCHEMA)
