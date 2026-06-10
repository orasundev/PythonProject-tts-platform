"""
Auth business logic: register, login, email verification, password reset.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.user import User
from app.schemas.auth import RegisterRequest
from app.utils.crypto import (
    create_access_token,
    create_refresh_token,
    generate_secure_token,
    hash_password,
    verify_password,
)
from app.utils.email import send_password_reset_email, send_verification_email


async def register_user(data: RegisterRequest, db: AsyncSession) -> User:
    # Check duplicate email
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Check duplicate slug
    slug_check = await db.execute(
        select(Organisation).where(Organisation.slug == data.organisation_slug)
    )
    if slug_check.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Organisation slug already taken")

    # Get free plan
    free_plan = await db.execute(select(Plan).where(Plan.name == "free"))
    free_plan = free_plan.scalar_one_or_none()

    # Create organisation
    org = Organisation(
        name=data.organisation_name,
        slug=data.organisation_slug,
        plan_id=free_plan.id if free_plan else None,
    )
    db.add(org)
    await db.flush()  # get org.id

    # Create verification token
    token = generate_secure_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=24)

    # Create user (owner of new org)
    user = User(
        organisation_id=org.id,
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role="owner",
        email_verification_token=token,
        email_verification_expires=expires,
    )
    db.add(user)
    await db.flush()

    # Send verification email (non-blocking; log failures)
    try:
        await send_verification_email(data.email, token)
    except Exception:
        pass  # Don't fail registration if email send fails

    return user


async def authenticate_user(email: str, password: str, db: AsyncSession) -> User:
    result = await db.execute(
        select(User).where(User.email == email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    return user


def issue_tokens(user: User) -> dict:
    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


async def verify_email(token: str, db: AsyncSession) -> User:
    result = await db.execute(
        select(User).where(User.email_verification_token == token)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification token")
    if user.email_verification_expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Verification token expired")
    user.is_email_verified = True
    user.email_verification_token = None
    user.email_verification_expires = None
    return user


async def initiate_password_reset(email: str, db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        return  # Silently ignore; don't reveal whether email exists

    token = generate_secure_token()
    user.password_reset_token = token
    user.password_reset_expires = datetime.now(timezone.utc) + timedelta(hours=1)
    try:
        await send_password_reset_email(email, token)
    except Exception:
        pass


async def complete_password_reset(token: str, new_password: str, db: AsyncSession) -> None:
    result = await db.execute(
        select(User).where(User.password_reset_token == token)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    if user.password_reset_expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Reset token expired")
    user.hashed_password = hash_password(new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
