"""Repository for SpinResult — pending slot spin outcomes.

A SpinResult token is created inside ``POST /slots/spin`` (and
``POST /slots/megaspin``) after the player's spins are deducted and the
outcome is rolled server-side. The frontend animates the reels to the
predetermined result and then calls ``POST /slots/victory`` with the
token's id; the server atomically redeems it (single-use, TTL-bounded)
before dispatching the background reward task. This eliminates
client-forgeable wins.

Storage: **Redis** with a 10-minute TTL. Tokens are short-lived handshake
data that should never accumulate; Redis gives us native TTL eviction and
atomic ``GETDEL`` single-redemption semantics without polluting PostgreSQL
or requiring a cleanup job.

Atomicity with the spin transaction: ``create`` is called from inside the
manager's ``get_session(commit=True)`` block *before* the PG transaction
commits. If the Redis write raises, the exception propagates out and the
session context rolls back — the player's spins are not debited.
Conversely, if PG commit fails after a successful Redis write, the orphan
token simply expires via TTL.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Optional

from utils.redis_client import get_redis
from utils.schemas import SpinResult

logger = logging.getLogger(__name__)

# Tokens live for 10 minutes — well over the longest plausible reel
# animation + network round-trip. Unredeemed tokens are evicted by Redis.
TTL_SECONDS = 600

_KEY_PREFIX = "spin_result:"


def _key(spin_result_id: str) -> str:
    return f"{_KEY_PREFIX}{spin_result_id}"


def create(
    *,
    user_id: int,
    chat_id: str,
    multiplier: int,
    win_type: str,
    rarity: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[int] = None,
    display_name: Optional[str] = None,
    set_id: Optional[int] = None,
    set_name: Optional[str] = None,
    is_megaspin: bool = False,
) -> SpinResult:
    """Persist a pending spin outcome and return its DTO (with server-issued id).

    Stores the JSON-serialized DTO under ``spin_result:{id}`` with a
    :data:`TTL_SECONDS` expiry. The id is a 128-bit UUID hex string —
    unforgeable in practice.
    """
    spin_result = SpinResult(
        id=uuid.uuid4().hex,
        user_id=user_id,
        chat_id=str(chat_id),
        multiplier=multiplier,
        win_type=win_type,
        rarity=rarity,
        source_type=source_type,
        source_id=source_id,
        display_name=display_name,
        set_id=set_id,
        set_name=set_name,
        is_megaspin=is_megaspin,
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    client = get_redis()
    client.set(_key(spin_result.id), spin_result.model_dump_json(), ex=TTL_SECONDS)
    return spin_result


def redeem(
    spin_result_id: str,
    user_id: int,
    chat_id: str,
) -> Optional[SpinResult]:
    """Atomically claim a pending spin outcome.

    Uses Redis ``GETDEL`` for atomic get-and-delete — even concurrent
    redemption attempts can only return the payload to one caller.

    Returns the SpinResult DTO on success, or None if:
      * The id does not exist (never issued, already redeemed, or TTL-expired).
      * The row belongs to a different user/chat (caller is impersonating).
        Note: in this case the token is *consumed* (since GETDEL deletes
        atomically). That's an acceptable trade-off because authenticated
        callers can't reach this function with a mismatched user_id — the
        endpoint validates the caller against the JWT before calling here.
        A successful mismatch would imply a bug or an authenticated user
        guessing another user's UUID, which we want to penalize anyway.
    """
    client = get_redis()
    # GETDEL atomically returns the value and deletes the key in one round-trip
    # (Redis >= 6.2; we run redis:7-alpine in compose).
    raw = client.getdel(_key(spin_result_id))
    if raw is None:
        return None
    try:
        spin_result = SpinResult.model_validate_json(raw)
    except Exception:
        logger.exception(
            "Failed to deserialize SpinResult %s payload from Redis", spin_result_id
        )
        return None
    if spin_result.user_id != user_id or spin_result.chat_id != str(chat_id):
        # GETDEL has already consumed the token at this point. This is
        # acceptable because authenticated callers can never reach here with a
        # mismatched user_id (the endpoint validates against the JWT first), so
        # a mismatch indicates a forged or guessed UUID — burning the token is
        # the desired response.
        logger.warning(
            "SpinResult %s rejected and discarded: user/chat mismatch (token=%s/%s, caller=%s/%s)",
            spin_result_id,
            spin_result.user_id,
            spin_result.chat_id,
            user_id,
            chat_id,
        )
        return None
    return spin_result

