"""Admin authentication endpoints.

Implements a two-step login flow:
1. ``POST /admin/auth/login`` — validate username + password, send OTP via Telegram.
2. ``POST /admin/auth/verify-otp`` — validate OTP, return JWT session token.
3. ``GET  /admin/auth/me`` — return current admin info (requires JWT).
"""

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from api.config import create_bot_instance
from api.dependencies import get_admin_user
from api.schemas import (
    AdminLoginRequest,
    AdminMeResponse,
    AdminOTPRequest,
    AdminTokenResponse,
)
from utils.services import admin_auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


@router.post("/login")
async def admin_login(body: AdminLoginRequest):
    """Step 1: Verify credentials and send an OTP to the admin's Telegram.

    Returns 200 with ``{"status": "otp_sent"}`` on success.
    """
    admin = await asyncio.to_thread(
        admin_auth_service.verify_credentials, body.username, body.password
    )
    if admin is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Generate OTP and deliver via Telegram
    otp_code = admin_auth_service.generate_otp(admin.id)

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


@router.post("/verify-otp", response_model=AdminTokenResponse)
async def admin_verify_otp(body: AdminOTPRequest):
    """Step 2: Verify the OTP and return a JWT session token."""
    admin_row = await asyncio.to_thread(admin_auth_service.get_admin_by_username, body.username)
    if admin_row is None:
        raise HTTPException(status_code=401, detail="Invalid username")

    ok = admin_auth_service.verify_otp(admin_row.id, body.code)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid or expired OTP")

    token = admin_auth_service.create_jwt(admin_row.id, admin_row.username)
    return AdminTokenResponse(token=token)


@router.get("/me", response_model=AdminMeResponse)
async def admin_me(payload: Dict[str, Any] = Depends(get_admin_user)):
    """Return the authenticated admin's info from the JWT."""
    return AdminMeResponse(
        admin_id=payload["sub"],
        username=payload["username"],
    )
