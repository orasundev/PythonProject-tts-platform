from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_org, require_role
from app.models.organisation import Organisation
from app.models.user import User
from app.schemas.billing import BillingPortalResponse, CheckoutSessionResponse
from app.services.billing_service import create_checkout_session, create_portal_session, handle_webhook

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def checkout_session(
    plan: str,
    user: User = Depends(require_role("owner")),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    url = await create_checkout_session(org, plan, db)
    return {"checkout_url": url}


@router.post("/portal", response_model=BillingPortalResponse)
async def billing_portal(
    user: User = Depends(require_role("owner")),
    org: Organisation = Depends(get_current_org),
):
    url = await create_portal_session(org)
    return {"portal_url": url}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Raw Stripe webhook — no JWT auth, verified by Stripe signature."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    return await handle_webhook(payload, sig_header, db)
