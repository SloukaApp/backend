from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.modules.users.dto import Email


class RegistrationRequest(BaseModel):
    email: Email
    password: str = Field(min_length=8, repr=False)
    consent: Literal[True]
    consent_version: str = Field(min_length=1, max_length=100, pattern=r"\S")

    @field_validator("consent", mode="before")
    @classmethod
    def require_explicit_consent(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Explicit consent is required")
        return value


class CredentialsRequest(BaseModel):
    email: Email
    password: str = Field(repr=False)


class LoginRequest(CredentialsRequest):
    installation_id: UUID


class ConfirmationRequest(BaseModel):
    token: str = Field(min_length=6, max_length=6, pattern=r"^[A-Za-z0-9]{6}$", repr=False)
    installation_id: UUID


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=256, repr=False)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(repr=False)
    new_password: str = Field(min_length=8, repr=False)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class DeliveryResponse(BaseModel):
    detail: str = "Confirmation email sent"


class DeviceResponse(BaseModel):
    id: UUID
    installation_id: UUID
    created_at: datetime
    last_authorized_at: datetime
    active: bool


class DevicesResponse(BaseModel):
    items: list[DeviceResponse]
    total: int
    limit: int
    offset: int
