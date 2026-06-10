"""
Integration tests for TTS generation:
- Successful generation
- Quota enforcement
- Voice access control
- SSML gating
- Async job creation
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


MOCK_AUDIO = b"ID3" + b"\x00" * 100  # fake MP3 bytes


@pytest.fixture
def mock_tts_generate():
    """Patch edge_tts.Communicate to avoid real network calls."""
    async def fake_stream():
        yield {"type": "audio", "data": MOCK_AUDIO}

    with patch("app.services.tts_service._generate_mp3", return_value=MOCK_AUDIO):
        with patch("app.utils.s3.upload_audio"):
            with patch("app.utils.s3.generate_presigned_url", return_value="https://s3.example.com/audio.mp3"):
                yield


# ── Basic generation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tts_generates_successfully(auth_client: AsyncClient, mock_tts_generate):
    response = await auth_client.post("/tts", json={
        "text": "Hello world",
        "voice": "en-US-AriaNeural",
        "rate": 0,
    })
    assert response.status_code == 200
    data = response.json()
    assert "file_id" in data
    assert "download_url" in data
    assert data["voice"] == "en-US-AriaNeural"
    assert data["character_count"] == len("Hello world")


@pytest.mark.asyncio
async def test_tts_empty_text_rejected(auth_client: AsyncClient):
    response = await auth_client.post("/tts", json={"text": "", "voice": "en-US-AriaNeural"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_tts_rate_out_of_range_rejected(auth_client: AsyncClient):
    response = await auth_client.post("/tts", json={
        "text": "Hello",
        "voice": "en-US-AriaNeural",
        "rate": 100,  # max is 50
    })
    assert response.status_code == 422


# ── Quota enforcement ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tts_exceeds_quota_returns_402(auth_client: AsyncClient, test_org, db):
    # Exhaust the quota
    test_org.chars_used_this_period = 10_000
    await db.commit()

    with patch("app.utils.s3.upload_audio"):
        with patch("app.utils.s3.generate_presigned_url", return_value="https://s3.example.com/audio.mp3"):
            response = await auth_client.post("/tts", json={
                "text": "Any text",
                "voice": "en-US-AriaNeural",
            })
    assert response.status_code == 402
    assert response.json()["detail"]["error"] == "quota_exceeded"


# ── Voice access ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tts_premium_voice_on_free_plan_returns_403(auth_client: AsyncClient):
    response = await auth_client.post("/tts", json={
        "text": "Hello",
        "voice": "de-DE-ConradNeural",  # not in free voices
    })
    assert response.status_code == 403


# ── SSML gating ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tts_ssml_on_free_plan_returns_403(auth_client: AsyncClient):
    response = await auth_client.post("/tts", json={
        "text": "<speak>Hello</speak>",
        "voice": "en-US-AriaNeural",
        "ssml": True,
    })
    assert response.status_code == 403


# ── Async job ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tts_long_text_creates_async_job(auth_client: AsyncClient, mock_tts_generate):
    """Text over 5000 chars should return 202 with a job_id."""
    long_text = "A" * 6000

    with patch("app.tasks.tts_tasks.generate_tts_job.apply_async") as mock_task:
        mock_task.return_value = MagicMock(id="celery-task-id-123")
        response = await auth_client.post("/tts", json={
            "text": long_text,
            "voice": "en-US-AriaNeural",
        })

    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "pending"
    assert "/jobs/" in data["status_url"]


@pytest.mark.asyncio
async def test_tts_x_async_header_creates_job(auth_client: AsyncClient):
    with patch("app.tasks.tts_tasks.generate_tts_job.apply_async") as mock_task:
        mock_task.return_value = MagicMock(id="celery-task-id-456")
        response = await auth_client.post(
            "/tts",
            json={"text": "Hello", "voice": "en-US-AriaNeural"},
            headers={"X-Async": "true"},
        )
    assert response.status_code == 200
    assert "job_id" in response.json()


# ── Download redirect ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_download_nonexistent_file_returns_404(auth_client: AsyncClient):
    response = await auth_client.get(f"/tts/download/{uuid.uuid4()}", follow_redirects=False)
    assert response.status_code == 404
