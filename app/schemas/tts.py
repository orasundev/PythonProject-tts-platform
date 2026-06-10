import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    voice: str = Field(default="en-US-AriaNeural")
    rate: int = Field(default=0, ge=-50, le=50)
    pitch: int | None = Field(default=None, ge=-50, le=50)
    volume: int | None = Field(default=None, ge=-50, le=50)
    ssml: bool = False
    output_format: Literal["mp3", "wav", "ogg"] = "mp3"


class TTSResponse(BaseModel):
    file_id: uuid.UUID
    download_url: str
    voice: str
    character_count: int
    output_format: str
    created_at: datetime


class AsyncTTSResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    status_url: str


class VoiceOut(BaseModel):
    short_name: str
    friendly_name: str
    locale: str
    gender: str
