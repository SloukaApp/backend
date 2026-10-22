from datetime import datetime, time
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, field_validator

from src.modules.users.domain import normalize_email, validate_timezone

Email = Annotated[str, AfterValidator(normalize_email)]
Password = Annotated[str, Field(min_length=8)]
Timezone = Annotated[str | None, AfterValidator(validate_timezone)]


class CreateUserInput(BaseModel):
    email: Email
    password: Password
    consent: Literal[True]
    consent_version: str = Field(min_length=1, max_length=100, pattern=r"\S")

    @field_validator("consent", mode="before")
    @classmethod
    def require_explicit_consent(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Explicit consent is required")
        return value


class UserState(BaseModel):
    id: UUID
    email: str
    email_confirmed: bool
    onboarding_completed: bool
    timezone: str | None
    reminders_enabled: bool
    reminder_time: time | None
    consent_version: str
    consent_accepted_at: datetime


class UpdateProfileInput(BaseModel):
    timezone: Timezone = None
    reminders_enabled: bool | None = None
    reminder_time: time | None = None
