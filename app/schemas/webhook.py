import uuid
from datetime import datetime

from pydantic import BaseModel, HttpUrl, Field


VALID_EVENTS = {
    "tts.completed",
    "tts.failed",
    "quota.warning",
    "quota.exceeded",
    "job.completed",
}


class WebhookCreate(BaseModel):
    url: HttpUrl
    events: list[str] = Field(min_length=1)

    def model_post_init(self, __context):
        invalid = set(self.events) - VALID_EVENTS
        if invalid:
            raise ValueError(f"Invalid events: {invalid}")


class WebhookOut(BaseModel):
    id: uuid.UUID
    url: str
    events: list[str]
    is_active: bool
    failure_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookTestResponse(BaseModel):
    message: str
    status_code: int | None
