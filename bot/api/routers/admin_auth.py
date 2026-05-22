"""Admin authentication endpoints.

Implements a two-step login flow:
1. ``POST /admin/auth/login`` — validate username + password, send OTP via Telegram.
2. ``POST /admin/auth/verify-otp`` — validate OTP, set HttpOnly session cookie.
3. ``POST /admin/auth/logout`` — clear the session cookie.
4. ``GET  /admin/auth/me`` — return current admin info (requires session).
"""

import asyncio
import datetime
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Response

from api.config import create_bot_instance
from api.cookies import (
    SESSION_HOURS_DEFAULT,
    SESSION_HOURS_REMEMBER,
    clear_session_cookie,
    set_session_cookie,
)
from api.dependencies import get_admin_user
from api.schemas import (
    AdminLoginRequest,
    AdminMeResponse,
    AdminOTPRequest,
    AdminVerifyResponse,
)
from repos import admin_auth_repo
from managers import auth_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


@router.post("/login")
async def admin_login(body: AdminLoginRequest):
    """Step 1: Verify credentials and send an OTP to the admin's Telegram.

    Returns 200 with ``{"status": "otp_sent"}`` on success.
    """
    admin = await asyncio.to_thread(
        auth_manager.verify_credentials, body.username, body.password
    )
    if admin is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Generate OTP and deliver via Telegram
    otp_code = admin_auth_repo.generate_otp(admin.id)

    try:
        bot = create_bot_instance()
        await bot.send_message(
            chat_id=admin.telegram_user_id,
            text=f"🔐 Your admin dashboard login code: <b>{otp_code}</b>\n\nThis code expires in 5 minutes.",
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("Failed to send OTP to Telegram user %s: %s", admin.telegram_user_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Failed to deliver OTP — check Telegram user ID configuration",
        )

    return {"status": "otp_sent"}


@router.post("/verify-otp", response_model=AdminVerifyResponse)
async def admin_verify_otp(body: AdminOTPRequest, response: Response):
    """Step 2: Verify the OTP and issue a session cookie."""
    admin_row = await asyncio.to_thread(admin_auth_repo.get_admin_by_username, body.username)
    if admin_row is None:
        raise HTTPException(status_code=401, detail="Invalid username")

    ok = admin_auth_repo.consume_otp(admin_row.id, body.code)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid or expired OTP")

    hours = SESSION_HOURS_REMEMBER if body.remember else SESSION_HOURS_DEFAULT
    token = auth_manager.create_jwt(admin_row.id, admin_row.username, expiry_hours=hours)
    set_session_cookie(response, token, max_age_seconds=hours * 3600)
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=hours)
    return AdminVerifyResponse(ok=True, expires_at=expires_at)


@router.post("/logout")
async def admin_logout(response: Response):
    """Clear the admin session cookie. Idempotent."""
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=AdminMeResponse)
async def admin_me(payload: Dict[str, Any] = Depends(get_admin_user)):
    """Return the authenticated admin's info from the session."""
    return AdminMeResponse(
        admin_id=payload["sub"],
        username=payload["username"],
    )
