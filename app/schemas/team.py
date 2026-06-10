import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="member", pattern="^(owner|admin|member)$")


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MemberOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime
    last_active_at: datetime | None

    model_config = {"from_attributes": True}


class AcceptInviteRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None
