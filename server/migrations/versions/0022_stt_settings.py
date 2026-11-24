"""Add sarvam_api_key and stt_provider to workspace_settings.

Adds two columns to ``identity.workspace_settings``:
- ``sarvam_api_key``: encrypted Sarvam STT API key (nullable, text)
- ``stt_provider``: speech-to-text provider selection (sarvam | web-speech
  | mock, default web-speech)
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0022_stt_settings"
down_revision = "0021_planning"
branch_labels = None
depends_on = None

SCHEMA = "identity"


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def _workspace_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["workspace_id"],
        ["identity.workspaces.id"],
        name=f"fk_{table}_workspace_id_workspaces",
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.add_column(
        "workspace_settings",
        sa.Column(
            "stt_provider",
            sa.String(20),
            nullable=False,
            server_default="web-speech",
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "workspace_settings",
        sa.Column(
            "sarvam_api_key",
            sa.String(512),
            nullable=True,
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("workspace_settings", "sarvam_api_key", schema=SCHEMA)
    op.drop_column("workspace_settings", "stt_provider", schema=SCHEMA)