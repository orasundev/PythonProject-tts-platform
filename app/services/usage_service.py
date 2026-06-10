"""
Usage analytics queries — all go through the database; summary is Redis-cached.
"""

import json
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.usage_log import UsageLog

settings = get_settings()
_redis_pool: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_pool


SUMMARY_TTL = 60  # seconds


async def get_usage_summary(org: Organisation, plan: Plan | None, db: AsyncSession) -> dict:
    cache_key = f"usage:summary:{org.id}"
    r = get_redis()

    cached = await r.get(cache_key)
    if cached:
        return json.loads(cached)

    # Count requests this period
    period_start = org.current_period_end - timedelta(days=30) if org.current_period_end else None

    query = select(func.count(UsageLog.id)).where(
        UsageLog.organisation_id == org.id,
        UsageLog.status == "success",
    )
    if period_start:
        query = query.where(UsageLog.created_at >= period_start)

    count_result = await db.execute(query)
    request_count = count_result.scalar_one() or 0

    limit = plan.monthly_char_limit if plan else 10_000
    chars_used = org.chars_used_this_period
    remaining = None if limit == -1 else max(0, limit - chars_used)

    summary = {
        "chars_used": chars_used,
        "chars_limit": limit,
        "chars_remaining": remaining,
        "request_count": request_count,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": org.current_period_end.isoformat() if org.current_period_end else None,
    }

    await r.setex(cache_key, SUMMARY_TTL, json.dumps(summary))
    return summary


async def invalidate_summary_cache(org_id) -> None:
    r = get_redis()
    await r.delete(f"usage:summary:{org_id}")


async def get_usage_history(
    org_id,
    db: AsyncSession,
    start: datetime | None = None,
    end: datetime | None = None,
    page: int = 1,
    limit: int = 50,
) -> dict:
    base = select(UsageLog).where(UsageLog.organisation_id == org_id)
    if start:
        base = base.where(UsageLog.created_at >= start)
    if end:
        base = base.where(UsageLog.created_at <= end)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    items_q = base.order_by(UsageLog.created_at.desc()).offset((page - 1) * limit).limit(limit)
    items = (await db.execute(items_q)).scalars().all()

    return {"items": items, "total": total, "page": page, "limit": limit}


async def get_usage_by_voice(org_id, db: AsyncSession) -> list[dict]:
    q = (
        select(
            UsageLog.voice,
            func.sum(UsageLog.character_count).label("total_chars"),
            func.count(UsageLog.id).label("request_count"),
        )
        .where(UsageLog.organisation_id == org_id, UsageLog.status == "success")
        .group_by(UsageLog.voice)
        .order_by(func.sum(UsageLog.character_count).desc())
    )
    rows = (await db.execute(q)).all()
    return [{"voice": r.voice, "total_chars": r.total_chars, "request_count": r.request_count} for r in rows]


async def get_daily_usage(org_id, db: AsyncSession) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    q = (
        select(
            func.date(UsageLog.created_at).label("date"),
            func.sum(UsageLog.character_count).label("total_chars"),
            func.count(UsageLog.id).label("request_count"),
        )
        .where(
            UsageLog.organisation_id == org_id,
            UsageLog.created_at >= cutoff,
            UsageLog.status == "success",
        )
        .group_by(func.date(UsageLog.created_at))
        .order_by(func.date(UsageLog.created_at))
    )
    rows = (await db.execute(q)).all()
    return [{"date": str(r.date), "total_chars": r.total_chars, "request_count": r.request_count} for r in rows]
