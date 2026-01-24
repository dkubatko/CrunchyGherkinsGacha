"""
Utilities for creating and validating short-lived download tokens.

These tokens use HMAC signatures so they don't require server-side storage,
making them safe for multi-worker deployments.
"""

import base64
import hashlib
import hmac
import time


def create_download_token(card_id: int, secret: str, ttl_seconds: int = 300) -> str:
    """Create a signed download token that doesn't require server-side storage.

    Args:
        card_id: The ID of the card to create a token for.
        secret: The secret key to sign the token with.
        ttl_seconds: How long the token is valid for (default: 5 minutes).

    Returns:
        A base64-encoded signed token string.
    """
    expires = int(time.time()) + ttl_seconds
    payload = f"{card_id}:{expires}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    token = base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()
    return token


def validate_download_token(token: str, card_id: int, secret: str) -> bool:
    """Validate a signed download token.

    Args:
        token: The token string to validate.
        card_id: The expected card ID the token should be for.
        secret: The secret key used to sign the token.

    Returns:
        True if the token is valid, False otherwise.
    """
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.split(":")
        if len(parts) != 3:
            return False

        token_card_id, expires_str, signature = parts
        if int(token_card_id) != card_id:
            return False

        expires = int(expires_str)
        if time.time() > expires:
            return False

        # Verify signature
        payload = f"{token_card_id}:{expires_str}"
        expected_sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(signature, expected_sig):
            return False

        return True
    except Exception:
        return False
