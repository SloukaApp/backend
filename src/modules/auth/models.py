from datetime import datetime
from uuid import UUID, uuid7

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import BaseModel


class Device(BaseModel):
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("user_id", "installation_id", name="uq_devices_user_installation"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    installation_id: Mapped[UUID]
    created_at: Mapped[datetime]
    last_authorized_at: Mapped[datetime]


class RefreshToken(BaseModel):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="refresh_expiry"),
        Index(
            "uq_refresh_tokens_current_device",
            "device_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]


class EmailConfirmation(BaseModel):
    __tablename__ = "email_confirmations"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="confirmation_expiry"),
        Index(
            "uq_email_confirmations_current_user",
            "user_id",
            unique=True,
            postgresql_where=text("consumed_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    consumed_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
