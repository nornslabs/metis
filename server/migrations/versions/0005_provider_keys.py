"""BYO provider keys and workspace settings in ``identity``.

``provider_keys`` holds one sealed key per workspace and kind (``llm``, ``exa``):
``sealed`` is the envelope-encrypted secret (base64 fields of ``SealedSecret``),
``masked`` its display form. ``workspace_settings`` holds per-workspace run
limits; a missing row means defaults. Both are tenant tables with RLS.
``metis_app`` gets DML through the default privileges from ``0004_app_role``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_provider_keys"
down_revision = "0004_app_role"
branch_labels = None
depends_on = None

SCHEMA = "identity"


def _timestamp(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def _workspace_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id"],
        ["identity.workspaces.id"],
        name=f"fk_{table}_workspace_id_workspaces",
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "provider_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("sealed", postgresql.JSONB(), nullable=False),
        sa.Column("masked", sa.Text(), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_provider_keys"),
        _workspace_fk("provider_keys"),
        sa.UniqueConstraint("workspace_id", "kind", name="uq_provider_keys_workspace_id_kind"),
        sa.CheckConstraint("kind IN ('llm', 'exa')", name="ck_provider_keys_kind"),
        schema=SCHEMA,
    )
    op.create_table(
        "workspace_settings",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_budget_usd", sa.Numeric(10, 2), nullable=False),
        sa.Column("max_steps", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("workspace_id", name="pk_workspace_settings"),
        _workspace_fk("workspace_settings"),
        schema=SCHEMA,
    )
    op.execute("SELECT enable_tenant_rls('identity.provider_keys'::regclass)")
    op.execute("SELECT enable_tenant_rls('identity.workspace_settings'::regclass)")


def downgrade() -> None:
    op.drop_table("workspace_settings", schema=SCHEMA)
    op.drop_table("provider_keys", schema=SCHEMA)
