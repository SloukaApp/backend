from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CodeEmail(BaseModel):
    message_id: UUID
    email: str = Field(repr=False)
    code: str = Field(repr=False)
    created_at: datetime
    expires_at: datetime
