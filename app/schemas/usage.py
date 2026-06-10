import uuid
from datetime import date, datetime

from pydantic import BaseModel


class UsageSummary(BaseModel):
    chars_used: int
    chars_limit: int          # -1 = unlimited
    chars_remaining: int | None   # None = unlimited
    request_count: int
    period_start: datetime | None
    period_end: datetime | None


class UsageLogOut(BaseModel):
    id: uuid.UUID
    voice: str
    character_count: int
    duration_ms: int | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedUsageLogs(BaseModel):
    items: list[UsageLogOut]
    total: int
    page: int
    limit: int


class VoiceBreakdown(BaseModel):
    voice: str
    total_chars: int
    request_count: int


class DailyAggregate(BaseModel):
    date: date
    total_chars: int
    request_count: int
