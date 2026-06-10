"""
Unit tests for cryptographic utilities:
- API key generation and hashing
- HMAC webhook signature
- JWT encode/decode
- Password hashing
"""

import hashlib

import pytest

from app.utils.crypto import (
    generate_api_key,
    generate_secure_token,
    hash_api_key,
    hash_password,
    make_key_prefix,
    sign_webhook_payload,
    verify_password,
    create_access_token,
    decode_token,
)


# ── API key generation ────────────────────────────────────────────────────────

def test_generate_api_key_live_prefix():
    full_key, key_hash = generate_api_key("live")
    assert full_key.startswith("tts_live_")


def test_generate_api_key_test_prefix():
    full_key, _ = generate_api_key("test")
    assert full_key.startswith("tts_test_")


def test_generate_api_key_hash_is_sha256():
    full_key, key_hash = generate_api_key("live")
    expected = hashlib.sha256(full_key.encode()).hexdigest()
    assert key_hash == expected
    assert len(key_hash) == 64


def test_generate_api_key_uniqueness():
    keys = {generate_api_key("live")[0] for _ in range(100)}
    assert len(keys) == 100  # all unique


def test_hash_api_key_deterministic():
    full_key, _ = generate_api_key("live")
    assert hash_api_key(full_key) == hash_api_key(full_key)


def test_make_key_prefix_masks_middle():
    full_key = "tts_live_Ab12Cd34Ef56Gh78Ij90Kl12Mn34"
    prefix = make_key_prefix(full_key)
    assert prefix.startswith("tts_live_")
    assert "..." in prefix
    # Raw key should not be fully visible
    assert full_key not in prefix


# ── HMAC webhook signature ────────────────────────────────────────────────────

def test_sign_webhook_payload_returns_hex():
    sig = sign_webhook_payload(b'{"event":"test"}', "my-secret")
    assert len(sig) == 64
    assert all(c in "0123456789abcdef" for c in sig)


def test_sign_webhook_payload_deterministic():
    payload = b'{"event":"tts.completed"}'
    secret = "super-secret"
    assert sign_webhook_payload(payload, secret) == sign_webhook_payload(payload, secret)


def test_sign_webhook_payload_different_secrets():
    payload = b'{"event":"test"}'
    sig1 = sign_webhook_payload(payload, "secret-1")
    sig2 = sign_webhook_payload(payload, "secret-2")
    assert sig1 != sig2


def test_sign_webhook_payload_different_payloads():
    secret = "shared-secret"
    sig1 = sign_webhook_payload(b"payload-a", secret)
    sig2 = sign_webhook_payload(b"payload-b", secret)
    assert sig1 != sig2


# ── Password hashing ──────────────────────────────────────────────────────────

def test_password_hash_and_verify():
    plain = "MySecurePassword!99"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)


def test_wrong_password_fails_verify():
    hashed = hash_password("correct-password")
    assert not verify_password("wrong-password", hashed)


def test_passwords_hash_differently():
    pw = "SamePassword"
    # bcrypt salts mean same password hashes differently each time
    assert hash_password(pw) != hash_password(pw)


# ── JWT ───────────────────────────────────────────────────────────────────────

def test_access_token_encodes_subject():
    token = create_access_token("user-id-123")
    payload = decode_token(token)
    assert payload["sub"] == "user-id-123"
    assert payload["type"] == "access"


def test_access_token_invalid_raises():
    from jose import JWTError
    with pytest.raises(JWTError):
        decode_token("not.a.valid.token")


def test_expired_token_raises():
    from datetime import timedelta
    from jose import jwt, JWTError
    from app.config import get_settings
    settings = get_settings()
    # Create token that expired 1 second ago
    from datetime import datetime, timezone
    payload = {
        "sub": "test",
        "type": "access",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(JWTError):
        decode_token(token)


# ── Secure token ──────────────────────────────────────────────────────────────

def test_generate_secure_token_is_unique():
    tokens = {generate_secure_token() for _ in range(100)}
    assert len(tokens) == 100


def test_generate_secure_token_min_length():
    token = generate_secure_token()
    assert len(token) >= 32
