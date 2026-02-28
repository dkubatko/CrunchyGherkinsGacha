"""Admin authentication service.

Provides credential verification, Telegram OTP generation/validation,
and JWT session token management for the admin dashboard.

OTP codes are stored in the ``admin_users`` database table so that all
gunicorn workers share the same state.

Usage::

    from utils.services import admin_auth_service

    user = admin_auth_service.verify_credentials("admin", "hunter2")
    if user:
        otp = admin_auth_service.generate_otp(user.id)
        # send otp to user.telegram_user_id via Telegram bot
        ...
        if admin_auth_service.consume_otp(user.id, submitted_code):
            token = admin_auth_service.create_jwt(user.id, user.username)
"""

from __future__ import annotations

import datetime
import logging
import os
import secrets
import time
from typing import Any, Dict, Optional

import bcrypt
import jwt

from utils.models import AdminUserModel
from utils.session import get_session

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

SERVER_SECRET: str = os.getenv("SERVER_SECRET", "")
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_HOURS = 24
_OTP_LENGTH = 6
_OTP_TTL_SECONDS = 5 * 60  # 5 minutes


# ── Credential helpers ───────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _check_password(plain: str, hashed: str) -> bool:
    """Verify *plain* against a bcrypt *hashed* value."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── Public API ───────────────────────────────────────────────────────────────


def verify_credentials(username: str, password: str) -> Optional[AdminUserModel]:
    """Validate username + password against the ``admin_users`` table.

    Returns the :class:`AdminUserModel` if credentials match, else ``None``.
    The returned object is **detached** from the session, but all scalar
    attributes remain accessible.
    """
    with get_session() as session:
        admin = session.query(AdminUserModel).filter(AdminUserModel.username == username).first()
        if admin is None:
            logger.warning("Admin login attempt with unknown username: %s", username)
            return None

        if not _check_password(password, admin.password_hash):
            logger.warning("Admin login attempt with wrong password for: %s", username)
            return None

        logger.info("Admin credentials verified for: %s", username)
        return admin


def get_admin_by_id(admin_id: int) -> Optional[AdminUserModel]:
    """Fetch an admin user by primary key."""
    with get_session() as session:
        return session.query(AdminUserModel).filter(AdminUserModel.id == admin_id).first()


def get_admin_by_username(username: str) -> Optional[AdminUserModel]:
    """Fetch an admin user by username (without password verification)."""
    with get_session() as session:
        return session.query(AdminUserModel).filter(AdminUserModel.username == username).first()


# ── OTP management ───────────────────────────────────────────────────────────


def generate_otp(admin_user_id: int) -> str:
    """Generate a 6-digit OTP for *admin_user_id* and persist it to the DB.

    Any previous OTP for the same user is overwritten.  Storing the OTP in
    the database (instead of in-memory) ensures all gunicorn workers share
    the same state.
    """
    code = "".join(secrets.choice("0123456789") for _ in range(_OTP_LENGTH))
    expiry = time.time() + _OTP_TTL_SECONDS

    with get_session() as session:
        admin = session.query(AdminUserModel).filter(AdminUserModel.id == admin_user_id).first()
        if admin is not None:
            admin.otp_code = code
            admin.otp_expires_at = expiry
            session.commit()

    logger.info(
        "OTP generated for admin_user_id=%s (expires in %ss)", admin_user_id, _OTP_TTL_SECONDS
    )
    return code


def consume_otp(admin_user_id: int, code: str) -> bool:
    """Validate and consume a previously generated OTP.

    Returns ``True`` if *code* matches and has not expired.  The OTP is
    always consumed (cleared) regardless of outcome to prevent replay.
    """
    with get_session() as session:
        admin = session.query(AdminUserModel).filter(AdminUserModel.id == admin_user_id).first()

        if admin is None or admin.otp_code is None:
            logger.warning(
                "OTP verification failed for admin_user_id=%s: no OTP pending", admin_user_id
            )
            return False

        stored_code = admin.otp_code
        expiry = admin.otp_expires_at

        # Always consume the OTP to prevent replay
        admin.otp_code = None
        admin.otp_expires_at = None
        session.commit()

    if expiry is not None and time.time() > expiry:
        logger.warning("OTP verification failed for admin_user_id=%s: expired", admin_user_id)
        return False

    if not secrets.compare_digest(code, stored_code):
        logger.warning("OTP verification failed for admin_user_id=%s: wrong code", admin_user_id)
        return False

    logger.info("OTP verified successfully for admin_user_id=%s", admin_user_id)
    return True


# ── JWT management ───────────────────────────────────────────────────────────


def create_jwt(admin_user_id: int, username: str) -> str:
    """Create a signed JWT for a verified admin session.

    The token contains ``sub`` (admin user ID), ``username``, ``iat``, and
    ``exp`` claims.
    """
    if not SERVER_SECRET:
        raise RuntimeError("SERVER_SECRET is not configured — cannot issue JWT")

    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(admin_user_id),
        "username": username,
        "iat": now,
        "exp": now + datetime.timedelta(hours=_JWT_EXPIRY_HOURS),
    }
    token = jwt.encode(payload, SERVER_SECRET, algorithm=_JWT_ALGORITHM)
    logger.info("JWT issued for admin_user_id=%s username=%s", admin_user_id, username)
    return token


def decode_jwt(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT.

    Returns the payload dict on success, or ``None`` if the token is
    invalid or expired.
    """
    if not SERVER_SECRET:
        logger.error("SERVER_SECRET is not configured — cannot decode JWT")
        return None

    try:
        payload = jwt.decode(token, SERVER_SECRET, algorithms=[_JWT_ALGORITHM])
        # sub was stored as a string to satisfy RFC 7519; cast back to int
        payload["sub"] = int(payload["sub"])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT decode failed: token expired")
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning("JWT decode failed: %s", exc)
        return None
