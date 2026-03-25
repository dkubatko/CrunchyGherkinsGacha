"""Admin authentication repository for database access to admin users and OTPs.

This module provides data access functions for admin user lookups
and OTP generation/consumption.
"""

from __future__ import annotations

import logging
import secrets
import time
from typing import Optional

import bcrypt
from sqlalchemy.orm import Session

from utils.models import AdminUserModel
from utils.schemas import AdminUser
from utils.session import with_session

logger = logging.getLogger(__name__)

_OTP_LENGTH = 6
_OTP_TTL_SECONDS = 5 * 60  # 5 minutes


@with_session
def get_admin_by_id(admin_id: int, *, session: Session) -> Optional[AdminUser]:
    """Fetch an admin user by primary key."""
    admin = session.query(AdminUserModel).filter(AdminUserModel.id == admin_id).first()
    return AdminUser.from_orm(admin) if admin else None


@with_session
def get_admin_by_username(username: str, *, session: Session) -> Optional[AdminUser]:
    """Fetch an admin user by username (without password verification)."""
    admin = session.query(AdminUserModel).filter(AdminUserModel.username == username).first()
    return AdminUser.from_orm(admin) if admin else None


@with_session
def verify_credentials(username: str, password: str, *, session: Session) -> Optional[AdminUser]:
    """Verify admin credentials. Returns AdminUser DTO if valid, None otherwise."""
    admin = session.query(AdminUserModel).filter_by(username=username).first()
    if not admin:
        return None
    if not bcrypt.checkpw(password.encode("utf-8"), admin.password_hash.encode("utf-8")):
        return None
    return AdminUser.from_orm(admin)


@with_session(commit=True)
def generate_otp(admin_user_id: int, *, session: Session) -> str:
    """Generate a 6-digit OTP for *admin_user_id* and persist it to the DB.

    Any previous OTP for the same user is overwritten.  Storing the OTP in
    the database (instead of in-memory) ensures all gunicorn workers share
    the same state.
    """
    code = "".join(secrets.choice("0123456789") for _ in range(_OTP_LENGTH))
    expiry = time.time() + _OTP_TTL_SECONDS

    admin = session.query(AdminUserModel).filter(AdminUserModel.id == admin_user_id).first()
    if admin is not None:
        admin.otp_code = code
        admin.otp_expires_at = expiry

    logger.info(
        "OTP generated for admin_user_id=%s (expires in %ss)", admin_user_id, _OTP_TTL_SECONDS
    )
    return code


@with_session(commit=True)
def consume_otp(admin_user_id: int, code: str, *, session: Session) -> bool:
    """Validate and consume a previously generated OTP.

    Returns ``True`` if *code* matches and has not expired.  The OTP is
    always consumed (cleared) regardless of outcome to prevent replay.
    """
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

    if expiry is not None and time.time() > expiry:
        logger.warning("OTP verification failed for admin_user_id=%s: expired", admin_user_id)
        return False

    if not secrets.compare_digest(code, stored_code):
        logger.warning("OTP verification failed for admin_user_id=%s: wrong code", admin_user_id)
        return False

    logger.info("OTP verified successfully for admin_user_id=%s", admin_user_id)
    return True
