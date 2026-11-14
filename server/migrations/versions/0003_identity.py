"""Identity tables: ``users``, ``workspaces`` and ``members``.

RLS only on ``members``: the ``tenant_isolation`` policy from ``enable_tenant_rls``
(rows of ``app.workspace_id``) plus a SELECT-only ``member_self`` policy (rows
of ``app.user_id``) so a user can list their memberships across workspaces.
Permissive policies OR together; with neither setting, no rows are visible.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_identity"
down_revision = "0002_core_outbox"
branch_labels = None
depends_on = None

SCHEMA = "identity"

MEMBER_SELF_POLICY = """
CREATE POLICY member_self ON identity.members FOR SELECT
USING (user_id = nullif(current_setting('app.user_id', true), '')::uuid)
"""


def _created_at() -> sa.Column[sa.DateTime]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("auth_sub", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("image", sa.Text(), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("auth_sub", name="uq_users_auth_sub"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        schema=SCHEMA,
    )
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_personal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_workspaces"),
        sa.ForeignKeyConstraint(
            ["created_by"], ["identity.users.id"], name="fk_workspaces_created_by_users"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_workspaces_personal_per_user",
        "workspaces",
        ["created_by"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("is_personal"),
    )
    op.create_table(
        "members",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("workspace_id", "user_id", name="pk_members"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["identity.workspaces.id"],
            name="fk_members_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["identity.users.id"],
            name="fk_members_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("role IN ('owner', 'member')", name="ck_members_role"),
        schema=SCHEMA,
    )
    op.create_index("ix_members_user_id", "members", ["user_id"], schema=SCHEMA)
    op.execute("SELECT enable_tenant_rls('identity.members'::regclass)")
    op.execute(MEMBER_SELF_POLICY)


def downgrade() -> None:
    op.drop_table("members", schema=SCHEMA)
    op.drop_index("uq_workspaces_personal_per_user", table_name="workspaces", schema=SCHEMA)
    op.drop_table("workspaces", schema=SCHEMA)
    op.drop_table("users", schema=SCHEMA)
