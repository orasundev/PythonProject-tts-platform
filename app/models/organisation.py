import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Organisation(Base):
    __tablename__ = "organisations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("active", "suspended", name="org_status_enum"),
        default="active",
        nullable=False,
    )

    # ── Billing ───────────────────────────────────────────────────────────
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subscription_status: Mapped[str] = mapped_column(
        String(50), default="free", nullable=False
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Usage tracking (reset each billing period) ────────────────────────
    chars_used_this_period: Mapped[int] = mapped_column(default=0, nullable=False)

    # ── Timestamps / soft-delete ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────
    users: Mapped[list["User"]] = relationship("User", back_populates="organisation")  # noqa: F821
    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="organisation")  # noqa: F821
    usage_logs: Mapped[list["UsageLog"]] = relationship("UsageLog", back_populates="organisation")  # noqa: F821
    generated_files: Mapped[list["GeneratedFile"]] = relationship("GeneratedFile", back_populates="organisation")  # noqa: F821
    webhooks: Mapped[list["Webhook"]] = relationship("Webhook", back_populates="organisation")  # noqa: F821
