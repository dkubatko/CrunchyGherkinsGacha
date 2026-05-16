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


def encode_single_card_token(card_id: int, chat_id: str) -> str:
    """Encode a single card payload for the mini app.

    Format: ``c-<chatId>-<cardId>``. The chat_id is included so the mini app
    can open the Hub in the correct chat context and decide between the
    Collection (owned) and All (chat-wide) tabs. ``chat_id`` may start with a
    leading dash for group chats; the decoder splits on the *last* dash to
    recover the card id.
    """
    if chat_id is None or str(chat_id) == "":
        raise ValueError("encode_single_card_token requires a chat_id")
    raw_token = f"c-{chat_id}-{card_id}"
    return _encode_token(raw_token)


def encode_single_aspect_token(aspect_id: int, chat_id: str) -> str:
    """Encode a single aspect payload for the mini app.

    Format: ``a-<chatId>-<aspectId>``. See :func:`encode_single_card_token`
    for details on chat_id handling.
    """
    if chat_id is None or str(chat_id) == "":
        raise ValueError("encode_single_aspect_token requires a chat_id")
    raw_token = f"a-{chat_id}-{aspect_id}"
    return _encode_token(raw_token)


def encode_casino_token(chat_id: str) -> str:
    """Encode a casino catalog payload for the mini app."""
    raw_token = f"casino-{chat_id}"
    return _encode_token(raw_token)
