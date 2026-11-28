"""Create one-time password reset reservations."""

import sqlalchemy as sa
from alembic import op

revision = "20261128_05"
down_revision = "20261128_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("expires_at > created_at", name=op.f("ck_password_resets_reset_expiry")),
    )
    op.create_index("ix_password_resets_user_created", "password_resets", ["user_id", "created_at"])
    op.create_index(
        "uq_password_resets_current_user",
        "password_resets",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("consumed_at IS NULL AND revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("password_resets")
