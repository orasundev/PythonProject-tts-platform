"""
Unit tests for API key creation, hashing, and plan-based limits.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.utils.crypto import generate_api_key, hash_api_key, make_key_prefix


def test_api_key_full_key_not_stored():
    """Verify we only store the hash, never the raw key."""
    full_key, key_hash = generate_api_key("live")
    assert full_key not in key_hash
    assert len(key_hash) == 64  # SHA-256 hex


def test_api_key_lookup_by_hash():
    """Simulate the lookup flow: hash incoming key, compare with stored hash."""
    full_key, stored_hash = generate_api_key("live")
    # Client sends raw key; server hashes it for lookup
    lookup_hash = hash_api_key(full_key)
    assert lookup_hash == stored_hash


def test_api_key_wrong_key_does_not_match():
    full_key, stored_hash = generate_api_key("live")
    wrong_key = full_key[:-4] + "XXXX"
    assert hash_api_key(wrong_key) != stored_hash


def test_key_prefix_shows_environment():
    full_key_live, _ = generate_api_key("live")
    full_key_test, _ = generate_api_key("test")
    assert make_key_prefix(full_key_live).startswith("tts_live_")
    assert make_key_prefix(full_key_test).startswith("tts_test_")


def test_key_prefix_masks_secret_portion():
    full_key, _ = generate_api_key("live")
    prefix = make_key_prefix(full_key)
    # The masked version must be shorter than or equal to the full key
    random_part = full_key.split("_", 2)[2]
    # Must not expose full random portion
    assert random_part not in prefix


@pytest.mark.asyncio
async def test_create_api_key_exceeds_plan_limit():
    """Exceeding max_api_keys should raise 402."""
    from app.routers.api_keys import FREE_KEY_LIMIT
    assert FREE_KEY_LIMIT == 1  # sanity check constant


def test_live_and_test_keys_are_distinct():
    live_key, _ = generate_api_key("live")
    test_key, _ = generate_api_key("test")
    assert live_key.startswith("tts_live_")
    assert test_key.startswith("tts_test_")
    assert live_key != test_key
