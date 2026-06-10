"""
TTS endpoints:
  POST /tts          — synchronous (or enqueues async job)
  GET  /tts/download/{file_id}  — pre-signed URL redirect
  GET  /voices
  GET  /jobs/{job_id}
"""

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_org, get_current_plan, get_current_user
from app.models.generated_file import GeneratedFile
from app.models.job import Job
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.user import User
from app.schemas.job import JobOut
from app.schemas.tts import AsyncTTSResponse, TTSRequest, TTSResponse, VoiceOut
from app.services.tts_service import generate_tts, list_voices
from app.utils.s3 import generate_presigned_url

router = APIRouter(tags=["tts"])

ASYNC_CHAR_THRESHOLD = 5_000


@router.get("/voices", response_model=list[VoiceOut])
async def get_voices(
    plan: Plan | None = Depends(get_current_plan),
    _user: User = Depends(get_current_user),
):
    voices = await list_voices(plan)
    return [
        VoiceOut(
            short_name=v["ShortName"],
            friendly_name=v.get("FriendlyName", v["ShortName"]),
            locale=v.get("Locale", ""),
            gender=v.get("Gender", ""),
        )
        for v in voices
    ]


@router.post("/tts")
async def text_to_speech(
    req: TTSRequest,
    x_async: str | None = Header(default=None, alias="X-Async"),
    user: User = Depends(get_current_user),
    org: Organisation = Depends(get_current_org),
    plan: Plan | None = Depends(get_current_plan),
    db: AsyncSession = Depends(get_db),
):
    force_async = (x_async or "").lower() == "true"
    should_async = force_async or len(req.text) > ASYNC_CHAR_THRESHOLD

    if should_async:
        # Business plan only (or large text fallback for all plans)
        job = Job(organisation_id=org.id, user_id=user.id)
        db.add(job)
        await db.flush()

        # Choose priority queue for Business plan
        from app.tasks.tts_tasks import generate_tts_job, generate_tts_job_priority
        task_fn = generate_tts_job_priority if (plan and plan.allows_priority_queue) else generate_tts_job
        celery_task = task_fn.apply_async(
            kwargs={
                "job_id": str(job.id),
                "request_data": req.model_dump(),
                "org_id": str(org.id),
                "user_id": str(user.id),
            }
        )
        job.celery_task_id = celery_task.id

        return AsyncTTSResponse(
            job_id=job.id,
            status="pending",
            status_url=f"/jobs/{job.id}",
        )

    result = await generate_tts(req, org, user, plan, db)
    return TTSResponse(**result)


@router.get("/tts/download/{file_id}")
async def download_file(
    file_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GeneratedFile).where(
            GeneratedFile.id == file_id,
            GeneratedFile.organisation_id == org.id,
        )
    )
    file = result.scalar_one_or_none()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    presigned_url = generate_presigned_url(file.s3_key)
    return RedirectResponse(url=presigned_url, status_code=302)


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job_status(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.organisation_id == org.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    download_url = None
    if job.status == "completed" and job.result_s3_key:
        # result_s3_key stores the file_id; resolve to presigned URL
        file_result = await db.execute(
            select(GeneratedFile).where(GeneratedFile.id == uuid.UUID(job.result_s3_key))
        )
        gen_file = file_result.scalar_one_or_none()
        if gen_file:
            download_url = generate_presigned_url(gen_file.s3_key)

    return JobOut(
        id=job.id,
        status=job.status,
        download_url=download_url,
        error=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
