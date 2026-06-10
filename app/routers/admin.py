"""
Super-admin endpoints — require is_superadmin = True.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_superadmin
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.user import User
from app.models.usage_log import UsageLog
from app.schemas.organisation import AdminOrgUpdate
from app.utils.email import send_announcement_email

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/orgs")
async def list_orgs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    _user: User = Depends(require_superadmin()),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count(Organisation.id)))).scalar_one()
    result = await db.execute(
        select(Organisation)
        .where(Organisation.deleted_at.is_(None))
        .order_by(Organisation.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    orgs = result.scalars().all()
    return {"items": orgs, "total": total, "page": page, "limit": limit}


@router.patch("/orgs/{org_id}")
async def update_org(
    org_id: uuid.UUID,
    data: AdminOrgUpdate,
    _user: User = Depends(require_superadmin()),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Organisation).where(Organisation.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    if data.status:
        org.status = data.status
    if data.plan_name:
        plan = (await db.execute(select(Plan).where(Plan.name == data.plan_name))).scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=400, detail=f"Unknown plan: {data.plan_name}")
        org.plan_id = plan.id

    return {"message": "Organisation updated"}


@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    _user: User = Depends(require_superadmin()),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count(User.id)))).scalar_one()
    result = await db.execute(
        select(User)
        .where(User.deleted_at.is_(None))
        .order_by(User.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    users = result.scalars().all()
    return {"items": users, "total": total, "page": page, "limit": limit}


@router.get("/usage")
async def platform_usage(
    _user: User = Depends(require_superadmin()),
    db: AsyncSession = Depends(get_db),
):
    total_requests = (await db.execute(select(func.count(UsageLog.id)))).scalar_one()
    total_chars = (await db.execute(select(func.sum(UsageLog.character_count)))).scalar_one() or 0
    total_orgs = (
        await db.execute(select(func.count(Organisation.id)).where(Organisation.deleted_at.is_(None)))
    ).scalar_one()
    return {
        "total_requests": total_requests,
        "total_chars": total_chars,
        "total_orgs": total_orgs,
    }


@router.post("/announcements")
async def broadcast_announcement(
    title: str,
    body: str,
    _user: User = Depends(require_superadmin()),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.deleted_at.is_(None), User.is_active.is_(True))
    )
    users = result.scalars().all()
    sent = 0
    for u in users:
        try:
            await send_announcement_email(u.email, title, body)
            sent += 1
        except Exception:
            pass
    return {"message": f"Announcement sent to {sent} users"}
