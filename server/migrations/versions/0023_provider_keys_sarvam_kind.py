"""Allow 'sarvam' kind in provider_keys check constraint.

Updates the ``ck_provider_keys_kind`` constraint on ``identity.provider_keys``
to include 'sarvam' alongside 'llm' and 'exa'.
"""

from alembic import op

revision = "0023_provider_keys_sarvam_kind"
down_revision = "0022_stt_settings"
branch_labels = None
depends_on = None

SCHEMA = "identity"


def upgrade() -> None:
    # Drop the existing check constraint
    op.execute(
        f"ALTER TABLE {SCHEMA}.provider_keys DROP CONSTRAINT ck_provider_keys_kind"
    )
    # Add the new check constraint including 'sarvam'
    op.execute(
        f"ALTER TABLE {SCHEMA}.provider_keys "
        f"ADD CONSTRAINT ck_provider_keys_kind "
        f"CHECK (kind IN ('llm', 'exa', 'sarvam'))"
    )


def downgrade() -> None:
    # Drop the updated check constraint
    op.execute(
        f"ALTER TABLE {SCHEMA}.provider_keys DROP CONSTRAINT ck_provider_keys_kind"
    )
    # Restore the original check constraint
    op.execute(
        f"ALTER TABLE {SCHEMA}.provider_keys "
        f"ADD CONSTRAINT ck_provider_keys_kind "
        f"CHECK (kind IN ('llm', 'exa'))"
    )