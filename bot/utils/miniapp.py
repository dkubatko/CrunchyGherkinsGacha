import base64
from typing import Optional

TOKEN_PREFIX = "tg1_"


def _encode_token(raw: str) -> str:
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{TOKEN_PREFIX}{encoded}"


def encode_miniapp_token(user_id: int, chat_id: Optional[str] = None) -> str:
    """Encode a user or user+chat payload for the mini app."""
    if chat_id:
        raw_token = f"uc-{user_id}-{chat_id}"
    else:
        raw_token = f"u-{user_id}"
    return _encode_token(raw_token)


def encode_single_card_token(card_id: int) -> str:
    """Encode a single card payload for the mini app."""
    raw_token = f"c-{card_id}"
    return _encode_token(raw_token)


def encode_casino_token(chat_id: str) -> str:
    """Encode a casino catalog payload for the mini app."""
    raw_token = f"casino-{chat_id}"
    return _encode_token(raw_token)
