"""
Async email delivery via aiosmtplib.
Templates use simple f-strings; swap with Jinja2 if you need richer HTML.
"""

import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from loguru import logger

from app.config import get_settings

settings = get_settings()


async def _send(to: str, subject: str, html_body: str) -> None:
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = settings.email_from
    message["To"] = to
    message.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            start_tls=settings.smtp_port == 587,
        )
    except Exception as exc:
        logger.error(f"Failed to send email to {to}: {exc}")
        raise


async def send_verification_email(to: str, token: str) -> None:
    verify_url = f"{settings.api_url}/auth/verify-email?token={token}"
    html = f"""
    <h2>Verify your email address</h2>
    <p>Click the link below to verify your email. This link expires in 24 hours.</p>
    <p><a href="{verify_url}">{verify_url}</a></p>
    """
    await _send(to, "Verify your TTS Platform email", html)


async def send_password_reset_email(to: str, token: str) -> None:
    reset_url = f"{settings.frontend_url}/reset-password?token={token}"
    html = f"""
    <h2>Reset your password</h2>
    <p>Click the link below to reset your password. This link expires in 1 hour.</p>
    <p><a href="{reset_url}">{reset_url}</a></p>
    <p>If you did not request a password reset, ignore this email.</p>
    """
    await _send(to, "Reset your TTS Platform password", html)


async def send_invitation_email(to: str, org_name: str, role: str, token: str) -> None:
    accept_url = f"{settings.frontend_url}/accept-invite?token={token}"
    html = f"""
    <h2>You've been invited to {org_name}</h2>
    <p>You have been invited to join <strong>{org_name}</strong> as <strong>{role}</strong>.</p>
    <p>Click below to accept the invitation. This link expires in 48 hours.</p>
    <p><a href="{accept_url}">{accept_url}</a></p>
    """
    await _send(to, f"Invitation to join {org_name} on TTS Platform", html)


async def send_announcement_email(to: str, title: str, body: str) -> None:
    html = f"<h2>{title}</h2><p>{body}</p>"
    await _send(to, f"[TTS Platform] {title}", html)
