"""remove stt_provider and sarvam_api_key from workspace_settings

Revision ID: 957fe3c9e5f8
Revises: 4993ebe4c0b9
Create Date: 2026-11-24 14:10:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '957fe3c9e5f8'
down_revision = '4993ebe4c0b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove stt_provider and sarvam_api_key columns from workspace_settings
    with op.batch_alter_table('workspace_settings', schema='identity') as batch_op:
        batch_op.drop_column('stt_provider')
        batch_op.drop_column('sarvam_api_key')


def downgrade() -> None:
    # Add back stt_provider and sarvam_api_key columns
    with op.batch_alter_table('workspace_settings', schema='identity') as batch_op:
        batch_op.add_column(
            sa.Column(
                'stt_provider',
                sa.String(20),
                default='web-speech',
                server_default='web-speech',
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column('sarvam_api_key', sa.String(512), nullable=True))