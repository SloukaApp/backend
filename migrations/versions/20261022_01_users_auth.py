"""Create user accounts and authentication records.

Revision ID: 20261022_01
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "20261022_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(1024), nullable=False),
        sa.Column("email_confirmed", sa.Boolean(), nullable=False),
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False),
        sa.Column("timezone", sa.String(255), nullable=True),
        sa.Column("reminders_enabled", sa.Boolean(), nullable=False),
        sa.Column("reminder_time", sa.Time(timezone=False), nullable=True),
        sa.Column("consent_version", sa.String(100), nullable=False),
        sa.Column("consent_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint(
            "length(consent_version) > 0", name=op.f("ck_users_consent_version_nonempty")
        ),
        sa.CheckConstraint(
            "NOT reminders_enabled OR (timezone IS NOT NULL AND reminder_time IS NOT NULL)",
            name=op.f("ck_users_reminder_configuration"),
        ),
    )
    op.create_table(
        "devices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "installation_id", name="uq_devices_user_installation"),
    )
    op.create_index("ix_devices_user_id", "devices", ["user_id"])
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("device_id", sa.Uuid(), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_refresh_tokens_refresh_expiry")
        ),
    )
    op.create_index("ix_refresh_tokens_device_id", "refresh_tokens", ["device_id"])
    op.create_index(
        "uq_refresh_tokens_current_device",
        "refresh_tokens",
        ["device_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_table(
        "email_confirmations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_email_confirmations_token_hash"),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_email_confirmations_confirmation_expiry")
        ),
    )
    op.create_index("ix_email_confirmations_user_id", "email_confirmations", ["user_id"])
    op.create_index(
        "uq_email_confirmations_current_user",
        "email_confirmations",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("consumed_at IS NULL AND revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("email_confirmations")
    op.drop_table("refresh_tokens")
    op.drop_table("devices")
    op.drop_table("users")
