from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_org, get_current_plan, get_current_user
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.user import User
from app.schemas.usage import DailyAggregate, PaginatedUsageLogs, UsageSummary, VoiceBreakdown
from app.services.usage_service import (
    get_daily_usage,
    get_usage_by_voice,
    get_usage_history,
    get_usage_summary,
)

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/summary", response_model=UsageSummary)
async def usage_summary(
    user: User = Depends(get_current_user),
    org: Organisation = Depends(get_current_org),
    plan: Plan | None = Depends(get_current_plan),
    db: AsyncSession = Depends(get_db),
):
    return await get_usage_summary(org, plan, db)


@router.get("/history", response_model=PaginatedUsageLogs)
async def usage_history(
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    user: User = Depends(get_current_user),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    return await get_usage_history(org.id, db, start, end, page, limit)


@router.get("/by-voice", response_model=list[VoiceBreakdown])
async def usage_by_voice(
    user: User = Depends(get_current_user),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    return await get_usage_by_voice(org.id, db)


@router.get("/daily", response_model=list[DailyAggregate])
async def daily_usage(
    user: User = Depends(get_current_user),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    return await get_daily_usage(org.id, db)
