"""
Authentication endpoints with IP-based rate limiting.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.services.auth_service import (
    authenticate_user,
    complete_password_reset,
    initiate_password_reset,
    issue_tokens,
    register_user,
    verify_email,
)
from app.utils.crypto import create_access_token, decode_token

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=MessageResponse, status_code=201)
@limiter.limit("5/15minutes")
async def register(request: Request, data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    await register_user(data, db)
    return {"message": "Registration successful. Please check your email to verify your account."}


@router.post("/login")
@limiter.limit("5/15minutes")
async def login(request: Request, data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(data.email, data.password, db)
    tokens = issue_tokens(user)

    # Set httpOnly cookies
    response.set_cookie(
        key="access_token",
        value=tokens["access_token"],
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=900,  # 15 min
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400 * 30,
    )
    return {"access_token": tokens["access_token"], "token_type": "bearer", "expires_in": 900}


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Logged out successfully"}


@router.post("/refresh")
@limiter.limit("5/15minutes")
async def refresh(request: Request, response: Response):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    new_access = create_access_token(payload["sub"])
    response.set_cookie(
        key="access_token",
        value=new_access,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=900,
    )
    return {"access_token": new_access, "token_type": "bearer", "expires_in": 900}


@router.get("/verify-email", response_model=MessageResponse)
async def verify_email_endpoint(token: str, db: AsyncSession = Depends(get_db)):
    await verify_email(token, db)
    return {"message": "Email verified successfully"}


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("5/15minutes")
async def forgot_password(request: Request, data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    await initiate_password_reset(data.email, db)
    return {"message": "If that email is registered, you will receive a reset link shortly."}


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/15minutes")
async def reset_password(request: Request, data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await complete_password_reset(data.token, data.new_password, db)
    return {"message": "Password reset successfully. You can now log in."}
