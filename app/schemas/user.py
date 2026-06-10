import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    role: str
    is_active: bool
    is_email_verified: bool
    organisation_id: uuid.UUID
    created_at: datetime
    last_active_at: datetime | None

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = None


class RoleUpdate(BaseModel):
    role: str  # owner | admin | member
