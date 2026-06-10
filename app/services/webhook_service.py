"""
Webhook delivery service.
Signing uses HMAC-SHA256; delivery is via Celery with exponential backoff.
"""

import json
import time
import uuid
from datetime import datetime, timezone

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import Webhook
from app.utils.crypto import sign_webhook_payload


async def dispatch_event(org_id: uuid.UUID, event: str, payload: dict, db: AsyncSession) -> None:
    """Find all active webhooks for the org that subscribe to this event and enqueue delivery."""
    from app.tasks.webhook_tasks import deliver_webhook  # avoid circular import

    result = await db.execute(
        select(Webhook).where(
            Webhook.organisation_id == org_id,
            Webhook.is_active.is_(True),
        )
    )
    webhooks = result.scalars().all()

    for wh in webhooks:
        if event in wh.events:
            deliver_webhook.apply_async(
                kwargs={
                    "webhook_id": str(wh.id),
                    "event": event,
                    "payload": payload,
                    "secret": wh.secret,
                    "url": wh.url,
                },
                queue="webhooks",
            )


def build_signed_payload(event: str, payload: dict, secret: str) -> tuple[bytes, str]:
    """Build the JSON body and compute the HMAC signature."""
    body = json.dumps({
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }).encode()
    signature = sign_webhook_payload(body, secret)
    return body, signature


async def deliver_now(url: str, body: bytes, signature: str) -> tuple[bool, int | None]:
    """Attempt a single HTTP POST; returns (success, status_code)."""
    headers = {
        "Content-Type": "application/json",
        "X-TTS-Signature": f"sha256={signature}",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, content=body, headers=headers)
        return resp.status_code < 400, resp.status_code
    except Exception as exc:
        logger.warning(f"Webhook delivery to {url} failed: {exc}")
        return False, None
