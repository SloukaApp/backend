"""Remove stored hashes for deterministically derived email confirmation codes."""

import sqlalchemy as sa
from alembic import op

revision = "20261128_04"
down_revision = "20261121_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_email_confirmations_token_hash", "email_confirmations", type_="unique")
    op.drop_column("email_confirmations", "token_hash")


def downgrade() -> None:
    op.add_column("email_confirmations", sa.Column("token_hash", sa.String(64), nullable=True))
    # Restore the old schema with unique values outside the SHA-256 hex format.
    op.execute("UPDATE email_confirmations SET token_hash = 'retired:' || id::text")
    op.alter_column(
        "email_confirmations", "token_hash", existing_type=sa.String(64), nullable=False
    )
    op.create_unique_constraint(
        "uq_email_confirmations_token_hash", "email_confirmations", ["token_hash"]
    )
