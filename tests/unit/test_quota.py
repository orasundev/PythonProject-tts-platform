"""
Unit tests for quota enforcement logic.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.services.tts_service import enforce_quota, enforce_plan_feature, enforce_voice_access, FREE_VOICES


def _make_org(chars_used: int = 0) -> Organisation:
    org = Organisation()
    org.id = uuid.uuid4()
    org.chars_used_this_period = chars_used
    return org


def _make_plan(limit: int, **kwargs) -> Plan:
    plan = Plan()
    plan.monthly_char_limit = limit
    plan.allows_ssml = kwargs.get("allows_ssml", False)
    plan.allows_all_voices = kwargs.get("allows_all_voices", False)
    plan.allows_webhooks = kwargs.get("allows_webhooks", False)
    plan.allows_priority_queue = kwargs.get("allows_priority_queue", False)
    return plan


# ── Quota enforcement ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quota_within_limit_passes():
    org = _make_org(chars_used=5000)
    plan = _make_plan(10_000)
    # Should not raise
    await enforce_quota(org, plan, 4000)


@pytest.mark.asyncio
async def test_quota_exact_limit_passes():
    org = _make_org(chars_used=0)
    plan = _make_plan(10_000)
    await enforce_quota(org, plan, 10_000)


@pytest.mark.asyncio
async def test_quota_exceeded_raises_402():
    from fastapi import HTTPException
    org = _make_org(chars_used=9_500)
    plan = _make_plan(10_000)
    with pytest.raises(HTTPException) as exc_info:
        await enforce_quota(org, plan, 600)
    assert exc_info.value.status_code == 402
    assert "quota_exceeded" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_unlimited_plan_never_raises():
    org = _make_org(chars_used=999_999_999)
    plan = _make_plan(-1)  # -1 = unlimited
    await enforce_quota(org, plan, 999_999)  # should not raise


@pytest.mark.asyncio
async def test_no_plan_uses_free_limit():
    from fastapi import HTTPException
    org = _make_org(chars_used=10_000)
    with pytest.raises(HTTPException) as exc_info:
        await enforce_quota(org, None, 1)
    assert exc_info.value.status_code == 402


# ── Plan feature gating ───────────────────────────────────────────────────────

def test_ssml_blocked_on_free_plan():
    from fastapi import HTTPException
    plan = _make_plan(10_000, allows_ssml=False)
    with pytest.raises(HTTPException) as exc_info:
        enforce_plan_feature(plan, "allows_ssml")
    assert exc_info.value.status_code == 403


def test_ssml_allowed_on_pro_plan():
    plan = _make_plan(500_000, allows_ssml=True)
    enforce_plan_feature(plan, "allows_ssml")  # should not raise


def test_webhooks_blocked_without_business_plan():
    from fastapi import HTTPException
    plan = _make_plan(500_000, allows_webhooks=False)
    with pytest.raises(HTTPException) as exc_info:
        enforce_plan_feature(plan, "allows_webhooks")
    assert exc_info.value.status_code == 403


def test_plan_gating_with_no_plan():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        enforce_plan_feature(None, "allows_ssml")
    assert exc_info.value.status_code == 403


# ── Voice access ─────────────────────────────────────────────────────────────

def test_free_voice_on_free_plan_allowed():
    free_voice = next(iter(FREE_VOICES))
    enforce_voice_access(None, free_voice)  # should not raise


def test_premium_voice_on_free_plan_blocked():
    from fastapi import HTTPException
    plan = _make_plan(10_000, allows_all_voices=False)
    premium_voice = "de-DE-ConradNeural"  # not in FREE_VOICES set
    with pytest.raises(HTTPException) as exc_info:
        enforce_voice_access(plan, premium_voice)
    assert exc_info.value.status_code == 403


def test_premium_voice_on_pro_plan_allowed():
    plan = _make_plan(500_000, allows_all_voices=True)
    enforce_voice_access(plan, "de-DE-ConradNeural")  # should not raise
