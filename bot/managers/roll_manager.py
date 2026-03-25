"""Roll manager — roll eligibility logic.

Determines whether a user is allowed to roll based on cooldown timing.
"""

from __future__ import annotations

import datetime
from datetime import timezone

from repos import roll_repo


def can_roll(user_id: int, chat_id: str) -> bool:
    """Check if a user can roll (24 hours since last roll) within a chat."""
    last_roll_time = roll_repo.get_last_roll_time(user_id, chat_id)
    if last_roll_time is None:
        return True

    time_since_last_roll = datetime.datetime.now(timezone.utc) - last_roll_time
    return time_since_last_roll.total_seconds() >= 24 * 60 * 60
