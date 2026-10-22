from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel

from src.modules.users.dto import Timezone


class ProfileResponse(BaseModel):
    id: UUID
    email: str
    email_confirmed: bool
    onboarding_completed: bool
    timezone: str | None
    reminders_enabled: bool
    reminder_time: time | None
    consent_version: str
    consent_accepted_at: datetime


class UpdateProfileRequest(BaseModel):
    timezone: Timezone = None
    reminders_enabled: bool | None = None
    reminder_time: time | None = None
