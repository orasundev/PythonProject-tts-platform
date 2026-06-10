"""
Celery tasks for async TTS generation (Business plan / large texts).
"""

import asyncio
import uuid

from loguru import logger

from app.tasks import celery_app


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="app.tasks.tts_tasks.generate_tts_job", max_retries=0)
def generate_tts_job(self, job_id: str, request_data: dict, org_id: str, user_id: str):
    """Standard queue TTS job."""
    return _run_async(_do_generate(job_id, request_data, org_id, user_id))


@celery_app.task(bind=True, name="app.tasks.tts_tasks.generate_tts_job_priority", max_retries=0)
def generate_tts_job_priority(self, job_id: str, request_data: dict, org_id: str, user_id: str):
    """Priority queue TTS job for Business plan."""
    return _run_async(_do_generate(job_id, request_data, org_id, user_id))


async def _do_generate(job_id: str, request_data: dict, org_id: str, user_id: str):
    from app.database import AsyncSessionLocal
    from app.models.job import Job
    from app.models.organisation import Organisation
    from app.models.plan import Plan
    from app.models.user import User
    from app.schemas.tts import TTSRequest
    from app.services.tts_service import generate_tts
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Load entities
        job = (await db.execute(select(Job).where(Job.id == uuid.UUID(job_id)))).scalar_one_or_none()
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        org = (await db.execute(select(Organisation).where(Organisation.id == uuid.UUID(org_id)))).scalar_one_or_none()
        user = (await db.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one_or_none()

        plan = None
        if org and org.plan_id:
            plan = (await db.execute(select(Plan).where(Plan.id == org.plan_id))).scalar_one_or_none()

        job.status = "processing"
        await db.commit()

        try:
            req = TTSRequest(**request_data)
            result = await generate_tts(req, org, user, plan, db)
            job.status = "completed"
            job.result_s3_key = str(result["file_id"])
            await db.commit()

            # Dispatch webhook
            from app.services.webhook_service import dispatch_event
            await dispatch_event(org.id, "job.completed", {"job_id": job_id}, db)
            await db.commit()

            logger.info(f"Async TTS job {job_id} completed")

        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)
            await db.commit()

            from app.services.webhook_service import dispatch_event
            try:
                await dispatch_event(org.id, "tts.failed", {"job_id": job_id, "error": str(exc)}, db)
                await db.commit()
            except Exception:
                pass

            logger.error(f"Async TTS job {job_id} failed: {exc}")
