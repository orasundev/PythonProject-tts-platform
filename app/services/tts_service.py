"""
TTS generation service:
- Quota enforcement
- edge_tts invocation (with rate/pitch/volume adjustments)
- Audio format conversion via pydub
- S3 upload and pre-signed URL generation
- Usage logging
"""

import asyncio
import io
import time
import uuid
from datetime import datetime, timedelta, timezone

import edge_tts
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.generated_file import GeneratedFile
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.usage_log import UsageLog
from app.models.user import User
from app.schemas.tts import TTSRequest
from app.utils.s3 import CONTENT_TYPE_MAP, build_s3_key, generate_presigned_url, upload_audio
from app.utils.ssml import validate_ssml

settings = get_settings()

# Default free plan limits (fallback when no plan row found)
FREE_CHAR_LIMIT = 10_000
FREE_VOICES = {
    "en-US-AriaNeural",
    "en-US-GuyNeural",
    "en-GB-SoniaNeural",
    "en-AU-NatashaNeural",
    "fr-FR-DeniseNeural",
    "de-DE-KatjaNeural",
}


async def enforce_quota(org: Organisation, plan: Plan | None, char_count: int) -> None:
    limit = plan.monthly_char_limit if plan else FREE_CHAR_LIMIT
    if limit == -1:
        return  # unlimited

    if org.chars_used_this_period + char_count > limit:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "quota_exceeded",
                "message": f"Monthly character quota of {limit:,} exceeded.",
                "chars_used": org.chars_used_this_period,
                "chars_limit": limit,
                "upgrade_url": f"{settings.frontend_url}/billing",
            },
        )


def enforce_plan_feature(plan: Plan | None, feature: str) -> None:
    """Raise 403 if the plan doesn't allow the feature."""
    allows = getattr(plan, feature, False) if plan else False
    if not allows:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "plan_restriction",
                "message": f"Feature '{feature}' is not available on your current plan.",
                "upgrade_url": f"{settings.frontend_url}/billing",
            },
        )


def enforce_voice_access(plan: Plan | None, voice: str) -> None:
    allows_all = plan.allows_all_voices if plan else False
    if not allows_all and voice not in FREE_VOICES:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "plan_restriction",
                "message": "This voice is only available on Pro and Business plans.",
                "upgrade_url": f"{settings.frontend_url}/billing",
            },
        )


def _build_rate_string(rate: int) -> str:
    """Convert integer (-50..+50) to edge_tts rate string like '+10%'."""
    sign = "+" if rate >= 0 else ""
    return f"{sign}{rate}%"


def _build_pitch_string(pitch: int) -> str:
    sign = "+" if pitch >= 0 else ""
    return f"{sign}{pitch}Hz"


def _build_volume_string(volume: int) -> str:
    sign = "+" if volume >= 0 else ""
    return f"{sign}{volume}%"


async def _generate_mp3(req: TTSRequest) -> bytes:
    """Run edge_tts and return raw MP3 bytes."""
    kwargs: dict = {
        "voice": req.voice,
        "rate": _build_rate_string(req.rate),
    }
    if req.pitch is not None:
        kwargs["pitch"] = _build_pitch_string(req.pitch)
    if req.volume is not None:
        kwargs["volume"] = _build_volume_string(req.volume)

    communicate = edge_tts.Communicate(req.text, **kwargs)

    mp3_chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_chunks.append(chunk["data"])

    return b"".join(mp3_chunks)


def _convert_audio(mp3_bytes: bytes, output_format: str) -> bytes:
    """Convert MP3 bytes to the requested format using pydub."""
    if output_format == "mp3":
        return mp3_bytes

    from pydub import AudioSegment

    audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
    out_buf = io.BytesIO()
    fmt = "ogg" if output_format == "ogg" else output_format
    audio.export(out_buf, format=fmt)
    return out_buf.getvalue()


async def generate_tts(
    req: TTSRequest,
    org: Organisation,
    user: User,
    plan: Plan | None,
    db: AsyncSession,
    api_key_id: uuid.UUID | None = None,
) -> dict:
    char_count = len(req.text)

    # ── Plan gates ────────────────────────────────────────────────────────
    if req.ssml:
        enforce_plan_feature(plan, "allows_ssml")
        validate_ssml(req.text)  # raises ValueError -> 422

    enforce_voice_access(plan, req.voice)

    if req.output_format != "mp3" or req.pitch is not None or req.volume is not None:
        enforce_plan_feature(plan, "allows_ssml")  # advanced options = Pro+

    await enforce_quota(org, plan, char_count)

    # ── Generate audio ────────────────────────────────────────────────────
    start_ms = int(time.monotonic() * 1000)
    try:
        mp3_bytes = await _generate_mp3(req)
        audio_bytes = _convert_audio(mp3_bytes, req.output_format)
        duration_ms = int(time.monotonic() * 1000) - start_ms
        tts_status = "success"
        error_msg = None
    except Exception as exc:
        duration_ms = int(time.monotonic() * 1000) - start_ms
        tts_status = "error"
        error_msg = str(exc)
        audio_bytes = b""

    # ── Upload to S3 ──────────────────────────────────────────────────────
    file_id = uuid.uuid4()
    s3_key = build_s3_key(org.id, file_id, req.output_format)

    if tts_status == "success":
        content_type = CONTENT_TYPE_MAP.get(req.output_format, "audio/mpeg")
        upload_audio(audio_bytes, s3_key, content_type)

    # ── Determine retention ───────────────────────────────────────────────
    retention_days = plan.file_retention_days if plan else 7
    expires_at = datetime.now(timezone.utc) + timedelta(days=retention_days)

    # ── Persist file record ───────────────────────────────────────────────
    gen_file = GeneratedFile(
        id=file_id,
        organisation_id=org.id,
        user_id=user.id,
        s3_key=s3_key,
        voice=req.voice,
        character_count=char_count,
        file_size_bytes=len(audio_bytes),
        output_format=req.output_format,
        expires_at=expires_at,
    )
    db.add(gen_file)

    # ── Log usage ─────────────────────────────────────────────────────────
    log = UsageLog(
        organisation_id=org.id,
        user_id=user.id,
        api_key_id=api_key_id,
        voice=req.voice,
        character_count=char_count,
        duration_ms=duration_ms,
        status=tts_status,
        error_message=error_msg,
    )
    db.add(log)

    # ── Update quota counter ──────────────────────────────────────────────
    if tts_status == "success":
        org.chars_used_this_period += char_count

    await db.flush()

    if tts_status == "error":
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {error_msg}")

    download_url = generate_presigned_url(s3_key)

    return {
        "file_id": file_id,
        "download_url": download_url,
        "voice": req.voice,
        "character_count": char_count,
        "output_format": req.output_format,
        "created_at": gen_file.created_at,
    }


async def list_voices(plan: Plan | None) -> list[dict]:
    """Return available voices based on the plan."""
    all_voices = await edge_tts.list_voices()
    if plan and plan.allows_all_voices:
        return all_voices
    # Filter to free voices only
    return [v for v in all_voices if v["ShortName"] in FREE_VOICES]
