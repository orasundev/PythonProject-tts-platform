"""
Stripe billing service: checkout sessions, portal, webhook event handling.
"""

import stripe
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.organisation import Organisation
from app.models.plan import Plan

settings = get_settings()
stripe.api_key = settings.stripe_secret_key


async def create_checkout_session(org: Organisation, plan_name: str, db: AsyncSession) -> str:
    price_id = settings.stripe_price_ids.get(plan_name)
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {plan_name}")

    # Create or reuse Stripe customer
    customer_id = org.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(metadata={"org_id": str(org.id)})
        customer_id = customer.id
        org.stripe_customer_id = customer_id

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.frontend_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.frontend_url}/billing/cancel",
        metadata={"org_id": str(org.id), "plan": plan_name},
    )
    return session.url


async def create_portal_session(org: Organisation) -> str:
    if not org.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer found for this organisation")

    session = stripe.billing_portal.Session.create(
        customer=org.stripe_customer_id,
        return_url=f"{settings.frontend_url}/billing",
    )
    return session.url


async def handle_webhook(payload: bytes, sig_header: str, db: AsyncSession) -> dict:
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data, db)
    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        await _handle_subscription_change(data, db)
    elif event_type == "invoice.payment_failed":
        await _handle_payment_failed(data, db)

    return {"received": True}


async def _handle_checkout_completed(session_obj: dict, db: AsyncSession) -> None:
    org_id = session_obj.get("metadata", {}).get("org_id")
    plan_name = session_obj.get("metadata", {}).get("plan")
    subscription_id = session_obj.get("subscription")

    if not org_id or not plan_name:
        return

    result = await db.execute(select(Organisation).where(Organisation.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        return

    plan_result = await db.execute(select(Plan).where(Plan.name == plan_name))
    plan = plan_result.scalar_one_or_none()

    org.stripe_subscription_id = subscription_id
    org.subscription_status = "active"
    if plan:
        org.plan_id = plan.id


async def _handle_subscription_change(sub_obj: dict, db: AsyncSession) -> None:
    customer_id = sub_obj.get("customer")
    result = await db.execute(
        select(Organisation).where(Organisation.stripe_customer_id == customer_id)
    )
    org = result.scalar_one_or_none()
    if not org:
        return

    status = sub_obj.get("status", "inactive")
    org.subscription_status = status

    if status in ("canceled", "unpaid"):
        # Downgrade to free
        free_plan = await db.execute(select(Plan).where(Plan.name == "free"))
        free = free_plan.scalar_one_or_none()
        if free:
            org.plan_id = free.id


async def _handle_payment_failed(invoice_obj: dict, db: AsyncSession) -> None:
    customer_id = invoice_obj.get("customer")
    result = await db.execute(
        select(Organisation).where(Organisation.stripe_customer_id == customer_id)
    )
    org = result.scalar_one_or_none()
    if org:
        org.subscription_status = "past_due"
