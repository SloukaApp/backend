from datetime import datetime, time
from uuid import UUID, uuid7

from sqlalchemy import Boolean, CheckConstraint, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import BaseModel


class User(BaseModel):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint("length(consent_version) > 0", name="consent_version_nonempty"),
        CheckConstraint(
            "NOT reminders_enabled OR (timezone IS NOT NULL AND reminder_time IS NOT NULL)",
            name="reminder_configuration",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    email: Mapped[str] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(String(1024))
    email_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    timezone: Mapped[str | None] = mapped_column(String(255))
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_time: Mapped[time | None] = mapped_column(Time(timezone=False))
    consent_version: Mapped[str] = mapped_column(String(100))
    consent_accepted_at: Mapped[datetime]
