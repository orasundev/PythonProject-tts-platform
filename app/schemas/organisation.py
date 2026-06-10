import uuid
from datetime import datetime

from pydantic import BaseModel


class OrganisationOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    logo_url: str | None
    status: str
    subscription_status: str
    current_period_end: datetime | None
    chars_used_this_period: int
    created_at: datetime

    model_config = {"from_attributes": True}


class OrganisationUpdate(BaseModel):
    name: str | None = None
    logo_url: str | None = None


class AdminOrgUpdate(BaseModel):
    status: str | None = None   # active | suspended
    plan_name: str | None = None
