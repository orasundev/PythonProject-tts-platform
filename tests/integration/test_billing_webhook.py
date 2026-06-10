"""
Integration tests for Stripe billing webhooks.
"""

import hashlib
import hmac
import json
import time
import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.config import get_settings

settings = get_settings()


def _make_stripe_sig(payload: bytes, secret: str) -> str:
    """Construct a valid Stripe webhook signature header."""
    timestamp = int(time.time())
    signed = f"{timestamp}.{payload.decode()}"
    sig = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


def _make_event(event_type: str, data: dict) -> dict:
    return {
        "id": f"evt_{uuid.uuid4().hex}",
        "type": event_type,
        "data": {"object": data},
    }


# ── Checkout completed ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkout_completed_activates_subscription(
    client: AsyncClient, test_org, pro_plan, db
):
    payload_obj = _make_event("checkout.session.completed", {
        "customer": "cus_test123",
        "subscription": "sub_test456",
        "metadata": {"org_id": str(test_org.id), "plan": "pro"},
    })
    payload = json.dumps(payload_obj).encode()
    sig = _make_stripe_sig(payload, settings.stripe_webhook_secret or "test-secret")

    with patch("stripe.Webhook.construct_event", return_value=payload_obj):
        response = await client.post(
            "/billing/webhook",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "stripe-signature": sig,
            },
        )

    assert response.status_code == 200
    await db.refresh(test_org)
    assert test_org.subscription_status == "active"
    assert test_org.stripe_subscription_id == "sub_test456"
    assert test_org.plan_id == pro_plan.id


# ── Subscription canceled ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subscription_deleted_downgrades_to_free(
    client: AsyncClient, test_org, free_plan, db
):
    # Set up org on pro plan
    test_org.stripe_customer_id = "cus_downgrade"
    test_org.subscription_status = "active"
    await db.commit()

    payload_obj = _make_event("customer.subscription.deleted", {
        "customer": "cus_downgrade",
        "status": "canceled",
    })
    payload = json.dumps(payload_obj).encode()

    with patch("stripe.Webhook.construct_event", return_value=payload_obj):
        response = await client.post(
            "/billing/webhook",
            content=payload,
            headers={"Content-Type": "application/json", "stripe-signature": "t=1,v1=x"},
        )

    assert response.status_code == 200
    await db.refresh(test_org)
    assert test_org.subscription_status == "canceled"
    assert test_org.plan_id == free_plan.id


# ── Payment failed ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_payment_failed_marks_past_due(client: AsyncClient, test_org, db):
    test_org.stripe_customer_id = "cus_pastdue"
    await db.commit()

    payload_obj = _make_event("invoice.payment_failed", {
        "customer": "cus_pastdue",
    })
    payload = json.dumps(payload_obj).encode()

    with patch("stripe.Webhook.construct_event", return_value=payload_obj):
        response = await client.post(
            "/billing/webhook",
            content=payload,
            headers={"Content-Type": "application/json", "stripe-signature": "t=1,v1=x"},
        )

    assert response.status_code == 200
    await db.refresh(test_org)
    assert test_org.subscription_status == "past_due"


# ── Invalid signature ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_stripe_signature_rejected(client: AsyncClient):
    import stripe
    payload = b'{"type":"checkout.session.completed"}'

    with patch(
        "stripe.Webhook.construct_event",
        side_effect=stripe.error.SignatureVerificationError("bad sig", sig_header="x"),
    ):
        response = await client.post(
            "/billing/webhook",
            content=payload,
            headers={"Content-Type": "application/json", "stripe-signature": "bad"},
        )

    assert response.status_code == 400
