"""
Celery tasks for webhook delivery with exponential backoff.
"""

import asyncio

from loguru import logger

from app.services.webhook_service import build_signed_payload, deliver_now
from app.tasks import celery_app


@celery_app.task(
    bind=True,
    name="app.tasks.webhook_tasks.deliver_webhook",
    max_retries=5,
    default_retry_delay=60,  # base delay; autoretry uses exponential backoff
)
def deliver_webhook(self, webhook_id: str, event: str, payload: dict, secret: str, url: str):
    """Deliver a signed webhook payload; retry up to 5 times with backoff."""
    loop = asyncio.new_event_loop()
    try:
        body, signature = build_signed_payload(event, payload, secret)
        success, status_code = loop.run_until_complete(deliver_now(url, body, signature))

        if not success:
            # Exponential backoff: 60, 120, 240, 480, 960 seconds
            retry_delay = 60 * (2 ** self.request.retries)
            logger.warning(f"Webhook {webhook_id} delivery failed (attempt {self.request.retries + 1}), retrying in {retry_delay}s")
            raise self.retry(countdown=retry_delay)

        logger.info(f"Webhook {webhook_id} delivered successfully ({status_code})")
    finally:
        loop.close()
