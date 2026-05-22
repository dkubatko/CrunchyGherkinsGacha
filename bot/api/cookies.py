"""Cookie helpers for admin session management.

Issues HttpOnly session cookies carrying the admin JWT. JavaScript cannot
read these cookies (mitigates XSS token theft), and the browser attaches
them automatically to API requests on the same site.
"""

from __future__ import annotations

import os

from fastapi import Response

ADMIN_SESSION_COOKIE = "admin_session"

# Session length presets (hours). Mirror what the JWT exp claim is signed for.
SESSION_HOURS_DEFAULT = 24
SESSION_HOURS_REMEMBER = 24 * 30  # 30 days


def _cookie_secure() -> bool:
    """Whether to set the Secure flag.

    Defaults to True in production. Local dev over plain http needs to opt out
    via ``ADMIN_COOKIE_SECURE=false`` so the browser will actually store the
    cookie.
    """
    raw = os.getenv("ADMIN_COOKIE_SECURE")
    if raw is None:
        # Match DEBUG_MODE default: insecure in debug, secure otherwise.
        return os.getenv("DEBUG_MODE", "false").lower() != "true"
    return raw.lower() in ("1", "true", "yes", "on")


def _cookie_samesite() -> str:
    """SameSite policy. 'lax' is the right balance for first-party admin UI."""
    return os.getenv("ADMIN_COOKIE_SAMESITE", "lax").lower()


def set_session_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    """Attach the admin session cookie to *response*."""
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=token,
        max_age=max_age_seconds,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Clear the admin session cookie."""
    response.delete_cookie(
        key=ADMIN_SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
    )
