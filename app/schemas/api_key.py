import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    environment: Literal["live", "test"] = "live"
    scopes: list[str] = Field(default=["tts:generate", "tts:download", "usage:read"])
    expires_at: datetime | None = None


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str      # masked display (prefix + first 8 + "..." + last 4)
    environment: str
    scopes: list[str]
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None

    model_config = {"from_attributes": True}


class ApiKeyCreatedOut(ApiKeyOut):
    """Returned only at creation time — includes the full raw key."""
    full_key: str


class ApiKeyUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
