import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    # -1 means unlimited
    monthly_char_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    max_api_keys: Mapped[int] = mapped_column(Integer, nullable=False)
    allows_ssml: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allows_all_voices: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allows_webhooks: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allows_priority_queue: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # File retention in days
    file_retention_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    # Monthly price in USD cents (0 = free)
    price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stripe_price_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
