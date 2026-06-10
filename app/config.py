"""
Application configuration loaded from environment variables / .env file.
All secrets are never logged; masking helpers live here too.
"""

import json
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────
    environment: Literal["development", "staging", "production"] = "development"
    api_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str
    test_database_url: str = ""

    # ── Redis ──────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── JWT / Security ─────────────────────────────────────────────────────
    secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # ── Stripe ─────────────────────────────────────────────────────────────
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_ids: dict[str, str] = {}

    @field_validator("stripe_price_ids", mode="before")
    @classmethod
    def parse_stripe_price_ids(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    # ── S3 ─────────────────────────────────────────────────────────────────
    s3_bucket: str = "tts-platform-audio"
    s3_endpoint_url: str = ""          # empty = default AWS
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"

    # ── Email ──────────────────────────────────────────────────────────────
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "noreply@example.com"

    # ── Sentry ─────────────────────────────────────────────────────────────
    sentry_dsn: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def mask_secret(value: str, *, prefix_len: int = 8, suffix_len: int = 4) -> str:
    """Show first 8 and last 4 characters, mask the rest with asterisks."""
    if len(value) <= prefix_len + suffix_len:
        return "*" * len(value)
    return value[:prefix_len] + "*" * (len(value) - prefix_len - suffix_len) + value[-suffix_len:]
