"""
Shared FastAPI dependency functions:
  - get_current_user  (JWT or API key)
  - require_role      (RBAC)
  - require_plan      (plan feature gating)
  - get_current_org
"""

import hashlib
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Callable

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.api_key import ApiKey
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.user import User
from app.utils.crypto import decode_token

settings = get_settings()

ROLE_HIERARCHY = {"owner": 3, "admin": 2, "member": 1}


async def _get_user_from_jwt(token: str, db: AsyncSession) -> User | None:
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
    except JWTError:
        return None

    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id), User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user and user.is_active:
        return user
    return None


async def _get_user_from_api_key(raw_key: str, db: AsyncSession) -> User | None:
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.hashed_secret == key_hash,
            ApiKey.is_active.is_(True),
            ApiKey.deleted_at.is_(None),
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        return None
    # Check expiry
    if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
        return None
    # Update last_used_at (fire-and-forget style; minor write)
    api_key.last_used_at = datetime.now(timezone.utc)
    await db.flush()

    user_result = await db.execute(
        select(User).where(User.id == api_key.user_id, User.deleted_at.is_(None))
    )
    user = user_result.scalar_one_or_none()
    return user if (user and user.is_active) else None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
    access_token: str | None = Cookie(default=None),
) -> User:
    """
    Authenticate via:
    1. Authorization: Bearer <jwt>  (JWT access token)
    2. Authorization: Bearer <tts_live_...>  (API key)
    3. access_token httpOnly cookie
    """
    token: str | None = None

    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    elif access_token:
        token = access_token

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    # Detect API key by prefix
    if token.startswith("tts_live_") or token.startswith("tts_test_"):
        user = await _get_user_from_api_key(token, db)
    else:
        user = await _get_user_from_jwt(token, db)

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired credentials")

    # Update activity timestamp
    user.last_active_at = datetime.now(timezone.utc)
    return user


async def get_current_org(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organisation:
    result = await db.execute(
        select(Organisation).where(
            Organisation.id == current_user.organisation_id,
            Organisation.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    if org.status == "suspended":
        raise HTTPException(status_code=403, detail="Your organisation has been suspended")
    return org


def require_role(*roles: str):
    """Dependency factory: require the user to have one of the given roles."""
    async def _dep(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles and not current_user.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {' or '.join(roles)}",
            )
        return current_user
    return _dep


def require_superadmin():
    async def _dep(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.is_superadmin:
            raise HTTPException(status_code=403, detail="Superadmin access required")
        return current_user
    return _dep


async def get_current_plan(
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> Plan | None:
    if not org.plan_id:
        return None
    result = await db.execute(select(Plan).where(Plan.id == org.plan_id))
    return result.scalar_one_or_none()
