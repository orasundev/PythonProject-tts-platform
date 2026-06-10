"""
Scheduled maintenance tasks:
- expire_old_files: delete S3 objects whose expires_at has passed
- reset_expired_quotas: reset chars_used_this_period for orgs whose billing period rolled over
"""

import asyncio
from datetime import datetime, timezone

from loguru import logger

from app.tasks import celery_app


@celery_app.task(name="app.tasks.maintenance_tasks.expire_old_files")
def expire_old_files():
    asyncio.new_event_loop().run_until_complete(_expire_files())


@celery_app.task(name="app.tasks.maintenance_tasks.reset_expired_quotas")
def reset_expired_quotas():
    asyncio.new_event_loop().run_until_complete(_reset_quotas())


async def _expire_files():
    from app.database import AsyncSessionLocal
    from app.models.generated_file import GeneratedFile
    from app.utils.s3 import delete_object
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(GeneratedFile).where(
                GeneratedFile.expires_at <= now,
                GeneratedFile.expires_at.isnot(None),
            )
        )
        expired = result.scalars().all()
        for f in expired:
            try:
                delete_object(f.s3_key)
            except Exception as exc:
                logger.warning(f"Failed to delete S3 object {f.s3_key}: {exc}")
            await db.delete(f)

        await db.commit()
        logger.info(f"Expired {len(expired)} generated files")


async def _reset_quotas():
    from app.database import AsyncSessionLocal
    from app.models.organisation import Organisation
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Organisation).where(
                Organisation.current_period_end <= now,
                Organisation.current_period_end.isnot(None),
                Organisation.deleted_at.is_(None),
            )
        )
        orgs = result.scalars().all()
        for org in orgs:
            org.chars_used_this_period = 0
            # Don't update current_period_end here — Stripe webhooks handle that

        await db.commit()
        logger.info(f"Reset quota counters for {len(orgs)} organisations")
