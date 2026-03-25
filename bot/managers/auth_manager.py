"""Auth manager — admin authentication logic.

Provides credential verification and JWT session token management
for the admin dashboard. Uses bcrypt for password hashing and PyJWT
for token creation/validation.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, Optional

import bcrypt
import jwt

from repos import admin_auth_repo
from utils.schemas import AdminUser

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_HOURS = 24


def _get_server_secret() -> str:
    """Lazy accessor for SERVER_SECRET to avoid circular imports at module level."""
    from api.config import SERVER_SECRET
    return SERVER_SECRET


# ── Credential helpers ───────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def _check_password(plain: str, hashed: str) -> bool:
    """Verify *plain* against a bcrypt *hashed* value."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── Public API ───────────────────────────────────────────────────────────────


def verify_credentials(username: str, password: str) -> Optional[AdminUser]:
    """Validate username + password against the ``admin_users`` table.

    Returns the :class:`AdminUser` DTO if credentials match, else ``None``.
    """
    admin = admin_auth_repo.verify_credentials(username, password)
    if admin is None:
        logger.warning("Admin login attempt failed for: %s", username)
        return None

    logger.info("Admin credentials verified for: %s", username)
    return admin


# ── JWT management ───────────────────────────────────────────────────────────


def create_jwt(admin_user_id: int, username: str) -> str:
    """Create a signed JWT for a verified admin session.

    The token contains ``sub`` (admin user ID), ``username``, ``iat``, and
    ``exp`` claims.
    """
    secret = _get_server_secret()
    if not secret:
        raise RuntimeError("SERVER_SECRET is not configured — cannot issue JWT")

    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(admin_user_id),
        "username": username,
        "iat": now,
        "exp": now + datetime.timedelta(hours=_JWT_EXPIRY_HOURS),
    }
    token = jwt.encode(payload, secret, algorithm=_JWT_ALGORITHM)
    logger.info("JWT issued for admin_user_id=%s username=%s", admin_user_id, username)
    return token


def decode_jwt(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT.

    Returns the payload dict on success, or ``None`` if the token is
    invalid or expired.
    """
    secret = _get_server_secret()
    if not secret:
        logger.error("SERVER_SECRET is not configured — cannot decode JWT")
        return None

    try:
        payload = jwt.decode(token, secret, algorithms=[_JWT_ALGORITHM])
        # sub was stored as a string to satisfy RFC 7519; cast back to int
        payload["sub"] = int(payload["sub"])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT decode failed: token expired")
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning("JWT decode failed: %s", exc)
        return None
