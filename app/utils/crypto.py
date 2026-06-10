"""
Cryptographic utilities: password hashing, JWT, API key generation, HMAC.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(subject: str, extra: dict | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire, "type": "access", **(extra or {})}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Raises JWTError on invalid / expired token."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


# ── API keys ──────────────────────────────────────────────────────────────────

def generate_api_key(environment: str = "live") -> tuple[str, str]:
    """
    Returns (full_key, sha256_hash).
    Full key is shown once; only the hash is stored.
    """
    prefix = f"tts_{environment}_"
    random_part = secrets.token_urlsafe(24)[:32]
    full_key = prefix + random_part
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, key_hash


def hash_api_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode()).hexdigest()


def make_key_prefix(full_key: str) -> str:
    """Return the displayable prefix: e.g. tts_live_Ab12Cd34...**Xy78"""
    parts = full_key.split("_", 2)
    env_prefix = "_".join(parts[:2]) + "_"  # "tts_live_"
    random_part = parts[2] if len(parts) > 2 else full_key
    if len(random_part) <= 12:
        return env_prefix + random_part
    return env_prefix + random_part[:8] + "..." + random_part[-4:]


# ── HMAC webhook signing ──────────────────────────────────────────────────────

def sign_webhook_payload(payload: bytes, secret: str) -> str:
    """Return hex-encoded HMAC-SHA256 signature."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


# ── Verification tokens ───────────────────────────────────────────────────────

def generate_secure_token() -> str:
    return secrets.token_urlsafe(32)
