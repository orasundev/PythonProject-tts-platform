"""
Integration tests for the full authentication flow:
register → verify email → login → refresh → logout → forgot/reset password
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient


# ── Register ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_creates_user(client: AsyncClient):
    slug = f"test-{uuid.uuid4().hex[:8]}"
    with patch("app.services.auth_service.send_verification_email", new_callable=AsyncMock):
        response = await client.post("/auth/register", json={
            "email": f"{slug}@example.com",
            "password": "SecurePass123!",
            "full_name": "Test User",
            "organisation_name": "Test Org",
            "organisation_slug": slug,
        })
    assert response.status_code == 201
    assert "Registration successful" in response.json()["message"]


@pytest.mark.asyncio
async def test_register_duplicate_email_fails(client: AsyncClient):
    slug = f"test-{uuid.uuid4().hex[:8]}"
    payload = {
        "email": f"{slug}@example.com",
        "password": "SecurePass123!",
        "full_name": "Test User",
        "organisation_name": "Org A",
        "organisation_slug": slug,
    }
    with patch("app.services.auth_service.send_verification_email", new_callable=AsyncMock):
        await client.post("/auth/register", json=payload)

    # Second registration with same email, different slug
    payload["organisation_slug"] = f"other-{uuid.uuid4().hex[:8]}"
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 400
    assert "Email already registered" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_duplicate_slug_fails(client: AsyncClient):
    slug = f"test-{uuid.uuid4().hex[:8]}"
    with patch("app.services.auth_service.send_verification_email", new_callable=AsyncMock):
        await client.post("/auth/register", json={
            "email": f"user1-{slug}@example.com",
            "password": "SecurePass123!",
            "organisation_name": "Org 1",
            "organisation_slug": slug,
        })
    response = await client.post("/auth/register", json={
        "email": f"user2-{slug}@example.com",
        "password": "SecurePass123!",
        "organisation_name": "Org 2",
        "organisation_slug": slug,  # same slug
    })
    assert response.status_code == 400


# ── Login ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_returns_token(client: AsyncClient, test_user):
    response = await client.post("/auth/login", json={
        "email": test_user.email,
        "password": "password123",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # Cookie should be set
    assert "access_token" in response.cookies


@pytest.mark.asyncio
async def test_login_wrong_password_fails(client: AsyncClient, test_user):
    response = await client.post("/auth/login", json={
        "email": test_user.email,
        "password": "wrong-password",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_fails(client: AsyncClient):
    response = await client.post("/auth/login", json={
        "email": "nobody@nowhere.com",
        "password": "password123",
    })
    assert response.status_code == 401


# ── Auth-protected endpoint ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_authenticated_request_succeeds(auth_client: AsyncClient):
    response = await auth_client.get("/usage/summary")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(client: AsyncClient):
    response = await client.get("/usage/summary")
    assert response.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_logout_clears_cookie(auth_client: AsyncClient):
    response = await auth_client.post("/auth/logout")
    assert response.status_code == 200
    # Cookie should be cleared (set with empty value / expired)
    assert response.cookies.get("access_token") in (None, "")


# ── Forgot / reset password ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forgot_password_always_returns_200(client: AsyncClient):
    """Should not reveal whether email exists."""
    response = await client.post("/auth/forgot-password", json={
        "email": "doesnotexist@example.com"
    })
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_with_valid_token(client: AsyncClient, test_user, db):
    from app.utils.crypto import generate_secure_token
    from datetime import datetime, timedelta, timezone

    token = generate_secure_token()
    test_user.password_reset_token = token
    test_user.password_reset_expires = datetime.now(timezone.utc) + timedelta(hours=1)
    await db.commit()

    response = await client.post("/auth/reset-password", json={
        "token": token,
        "new_password": "NewPassword456!",
    })
    assert response.status_code == 200

    # Should be able to log in with new password
    login = await client.post("/auth/login", json={
        "email": test_user.email,
        "password": "NewPassword456!",
    })
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_invalid_token_fails(client: AsyncClient):
    response = await client.post("/auth/reset-password", json={
        "token": "invalid-token-xyz",
        "new_password": "NewPassword456!",
    })
    assert response.status_code == 400
