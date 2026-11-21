"""merge heads

Revision ID: 3aaa8e5afd8c
Revises: 0018_manual_refresh_runs, 0019_manual_refresh_runs
Create Date: 2026-11-21 06:51:34.602230

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '3aaa8e5afd8c'
down_revision: str | Sequence[str] | None = ('0018_manual_refresh_runs', '0019_manual_refresh_runs')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
