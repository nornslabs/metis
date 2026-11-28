"""Migration ``0029_spec_hlds``: the high-level design written for a spec version.

Table ``ideas.spec_hlds``: the HLD (markdown) the Architect wrote for one version of a software
idea's spec, with the build language it names and a hash of the spec text it was written for
(so the API can tell when the spec has since changed). At most one per ``(idea_id,
spec_version_number)``. Tenant table with RLS. ``metis_app`` gets ``SELECT`` and ``INSERT`` only,
so an HLD cannot be changed or deleted through the app role; a new spec text gets a new row.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029_spec_hlds"
down_revision = "0028_idea_project_name"
branch_labels = None
depends_on = None

APP_ROLE = "metis_app"
SCHEMA = "ideas"
TABLE = "spec_hlds"


def _uuid(name: str) -> sa.Column[object]:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=False)


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    op.create_table(
        TABLE,
        _uuid("id"),
        _uuid("workspace_id"),
        _uuid("idea_id"),
        sa.Column("spec_version_number", sa.Integer(), nullable=False),
        sa.Column("spec_hash", sa.Text(), nullable=False),
        sa.Column("build_language", sa.Text(), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name=f"pk_{TABLE}"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["identity.workspaces.id"],
            name=f"fk_{TABLE}_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["idea_id"],
            [f"{SCHEMA}.ideas.id"],
            name=f"fk_{TABLE}_idea_id_ideas",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("spec_version_number >= 1", name=f"ck_{TABLE}_number"),
        sa.CheckConstraint(
            "char_length(build_language) BETWEEN 1 AND 100", name=f"ck_{TABLE}_build_language"
        ),
        sa.CheckConstraint("char_length(content_md) >= 1", name=f"ck_{TABLE}_content"),
        sa.UniqueConstraint("idea_id", "spec_version_number", name=f"uq_{TABLE}_idea_number"),
        schema=SCHEMA,
    )
    op.create_index(
        f"ix_{TABLE}_workspace_idea",
        TABLE,
        ["workspace_id", "idea_id", sa.text("spec_version_number DESC")],
        schema=SCHEMA,
    )
    op.execute(f"SELECT enable_tenant_rls('{SCHEMA}.{TABLE}'::regclass)")
    op.execute(f"REVOKE ALL ON {SCHEMA}.{TABLE} FROM {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON {SCHEMA}.{TABLE} TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
