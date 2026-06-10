import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_org, get_current_user, require_role
from app.models.invitation import Invitation
from app.models.organisation import Organisation
from app.models.user import User
from app.schemas.team import AcceptInviteRequest, InvitationOut, InviteRequest, MemberOut
from app.utils.crypto import generate_secure_token, hash_password
from app.utils.email import send_invitation_email

router = APIRouter(prefix="/team", tags=["team"])


@router.post("/invite", response_model=InvitationOut, status_code=201)
async def invite_member(
    data: InviteRequest,
    user: User = Depends(require_role("owner", "admin")),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    token = generate_secure_token()
    invitation = Invitation(
        organisation_id=org.id,
        invited_by_user_id=user.id,
        email=data.email,
        role=data.role,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
    )
    db.add(invitation)
    await db.flush()

    try:
        await send_invitation_email(data.email, org.name, data.role, token)
    except Exception:
        pass

    return invitation


@router.post("/accept-invite")
async def accept_invite(
    data: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Invitation).where(
            Invitation.token == data.token,
            Invitation.accepted_at.is_(None),
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=400, detail="Invalid or already-used invitation")
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation expired")

    # Check if user already exists
    existing = await db.execute(select(User).where(User.email == invite.email))
    existing_user = existing.scalar_one_or_none()

    if existing_user:
        # Move existing user to the org
        existing_user.organisation_id = invite.organisation_id
        existing_user.role = invite.role
    else:
        new_user = User(
            organisation_id=invite.organisation_id,
            email=invite.email,
            full_name=data.full_name,
            hashed_password=hash_password(data.password),
            role=invite.role,
            is_email_verified=True,  # Invite link counts as verification
        )
        db.add(new_user)

    invite.accepted_at = datetime.now(timezone.utc)
    return {"message": "Invitation accepted successfully"}


@router.get("/members", response_model=list[MemberOut])
async def list_members(
    user: User = Depends(get_current_user),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(
            User.organisation_id == org.id,
            User.deleted_at.is_(None),
        ).order_by(User.created_at)
    )
    return result.scalars().all()


@router.patch("/members/{target_user_id}")
async def update_member_role(
    target_user_id: uuid.UUID,
    data: dict,  # {"role": "admin"}
    user: User = Depends(require_role("owner", "admin")),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    # Admins cannot promote to owner
    new_role = data.get("role")
    if new_role not in ("owner", "admin", "member"):
        raise HTTPException(status_code=400, detail="Invalid role")
    if new_role == "owner" and user.role != "owner":
        raise HTTPException(status_code=403, detail="Only owners can assign the owner role")

    result = await db.execute(
        select(User).where(User.id == target_user_id, User.organisation_id == org.id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")
    target.role = new_role
    return {"message": f"Role updated to {new_role}"}


@router.delete("/members/{target_user_id}", status_code=204)
async def remove_member(
    target_user_id: uuid.UUID,
    user: User = Depends(require_role("owner", "admin")),
    org: Organisation = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.id == target_user_id, User.organisation_id == org.id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")

    # Prevent removing the last owner
    if target.role == "owner":
        owners = await db.execute(
            select(User).where(
                User.organisation_id == org.id,
                User.role == "owner",
                User.deleted_at.is_(None),
            )
        )
        owner_count = len(owners.scalars().all())
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last owner")

    from datetime import datetime, timezone
    target.deleted_at = datetime.now(timezone.utc)
    target.is_active = False
