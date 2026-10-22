from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ConfirmationDelivery(BaseModel):
    email: str = Field(repr=False)
    token: str = Field(repr=False)


class TokenPair(BaseModel):
    access_token: str = Field(repr=False)
    refresh_token: str = Field(repr=False)
    token_type: str = "bearer"
    expires_in: int = 1800


class Principal(BaseModel):
    user_id: UUID
    device_id: UUID


class DeviceInfo(BaseModel):
    id: UUID
    installation_id: UUID
    created_at: datetime
    last_authorized_at: datetime
    active: bool


class DevicePage(BaseModel):
    items: list[DeviceInfo]
    total: int
    limit: int
    offset: int
