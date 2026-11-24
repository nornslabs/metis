"""merge sarvam stt and linear integrations

Revision ID: 4993ebe4c0b9
Revises: 0023_provider_keys_sarvam_kind, 0025_workspace_linear_team
Create Date: 2026-11-24 07:51:34.602230

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '4993ebe4c0b9'
down_revision: str | Sequence[str] | None = (
    '0023_provider_keys_sarvam_kind', '0025_workspace_linear_team'
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass