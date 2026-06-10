import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import mask_secret
from app.database import get_db
from app.dependencies import get_current_org, get_current_user, require_role
from app.models.api_key import ApiKey
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.user import User
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreatedOut, ApiKeyOut, ApiKeyUpdate
from app.utils.crypto import generate_api_key, make_key_prefix

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

FREE_KEY_LIMIT = 1


async def _get_plan(org: Organisation, db: AsyncSession) -> Plan | None:
    if not org.plan_id:
        return None
    result = await db.execute(select(Plan).where(Plan.id == org.plan_id))
    return result.scalar_one_or_none()


@router.post("", response_model=ApiKeyCreatedOut, status_code=201)
async def create_api_key(
    data: ApiKeyCreate,
    user: User = Depends(require_role("owner", "admin")),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    plan = await _get_plan(org, db)
    max_keys = plan.max_api_keys if plan else FREE_KEY_LIMIT

    # Count existing active keys
    count_result = await db.execute(
        select(ApiKey).where(
            ApiKey.organisation_id == org.id,
            ApiKey.is_active.is_(True),
            ApiKey.deleted_at.is_(None),
        )
    )
    existing = count_result.scalars().all()
    if len(existing) >= max_keys:
        raise HTTPException(
            status_code=402,
            detail=f"API key limit ({max_keys}) reached for your plan. Upgrade to create more.",
        )

    full_key, key_hash = generate_api_key(data.environment)
    key_prefix = make_key_prefix(full_key)

    api_key = ApiKey(
        organisation_id=org.id,
        user_id=user.id,
        name=data.name,
        key_prefix=key_prefix,
        hashed_secret=key_hash,
        environment=data.environment,
        scopes=data.scopes,
        expires_at=data.expires_at,
    )
    db.add(api_key)
    await db.flush()

    out = ApiKeyCreatedOut.model_validate(api_key)
    out.full_key = full_key  # shown only once
    return out


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    user: User = Depends(get_current_user),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.organisation_id == org.id,
            ApiKey.deleted_at.is_(None),
        ).order_by(ApiKey.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/{key_id}", status_code=204)
async def delete_api_key(
    key_id: uuid.UUID,
    user: User = Depends(require_role("owner", "admin")),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.organisation_id == org.id)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    key.deleted_at = datetime.now(timezone.utc)
    key.is_active = False


@router.patch("/{key_id}", response_model=ApiKeyOut)
async def update_api_key(
    key_id: uuid.UUID,
    data: ApiKeyUpdate,
    user: User = Depends(require_role("owner", "admin")),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.organisation_id == org.id,
            ApiKey.deleted_at.is_(None),
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")

    if data.name is not None:
        key.name = data.name
    if data.is_active is not None:
        key.is_active = data.is_active
    return key
