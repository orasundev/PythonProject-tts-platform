import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_org, get_current_user, require_role
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.user import User
from app.models.webhook import Webhook
from app.schemas.webhook import WebhookCreate, WebhookOut, WebhookTestResponse
from app.services.webhook_service import build_signed_payload, deliver_now

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

MAX_WEBHOOKS = 10


async def _enforce_webhook_plan(org: Organisation, db: AsyncSession) -> None:
    if not org.plan_id:
        raise HTTPException(status_code=403, detail="Webhooks require a Business plan")
    plan = (await db.execute(select(Plan).where(Plan.id == org.plan_id))).scalar_one_or_none()
    if not plan or not plan.allows_webhooks:
        raise HTTPException(
            status_code=403,
            detail="Webhooks are only available on the Business plan",
        )


@router.post("", response_model=WebhookOut, status_code=201)
async def create_webhook(
    data: WebhookCreate,
    user: User = Depends(require_role("owner", "admin")),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    await _enforce_webhook_plan(org, db)

    count_result = await db.execute(
        select(Webhook).where(Webhook.organisation_id == org.id, Webhook.is_active.is_(True))
    )
    if len(count_result.scalars().all()) >= MAX_WEBHOOKS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_WEBHOOKS} webhooks allowed")

    wh = Webhook(
        organisation_id=org.id,
        url=str(data.url),
        secret=secrets.token_hex(32),
        events=data.events,
    )
    db.add(wh)
    await db.flush()
    return wh


@router.get("", response_model=list[WebhookOut])
async def list_webhooks(
    user: User = Depends(require_role("owner", "admin")),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Webhook).where(Webhook.organisation_id == org.id).order_by(Webhook.created_at)
    )
    return result.scalars().all()


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: uuid.UUID,
    user: User = Depends(require_role("owner", "admin")),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Webhook).where(Webhook.id == webhook_id, Webhook.organisation_id == org.id)
    )
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.delete(wh)


@router.post("/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    webhook_id: uuid.UUID,
    user: User = Depends(require_role("owner", "admin")),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Webhook).where(Webhook.id == webhook_id, Webhook.organisation_id == org.id)
    )
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    body, signature = build_signed_payload("test", {"message": "This is a test delivery"}, wh.secret)
    success, status_code = await deliver_now(wh.url, body, signature)

    return WebhookTestResponse(
        message="Test delivered successfully" if success else "Test delivery failed",
        status_code=status_code,
    )
