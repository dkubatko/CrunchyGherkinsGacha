"""Roll service for tracking user roll timestamps.

This module provides all roll-related business logic including
checking roll eligibility and recording rolls.
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from utils.models import UserRollModel
from utils.session import get_session

logger = logging.getLogger(__name__)


def get_last_roll_time(user_id: int, chat_id: str) -> Optional[datetime.datetime]:
    """Get the last roll timestamp for a user within a specific chat."""
    with get_session() as session:
        roll = (
            session.query(UserRollModel)
            .filter(
                UserRollModel.user_id == user_id,
                UserRollModel.chat_id == str(chat_id),
            )
            .first()
        )
        if roll and roll.last_roll_timestamp:
            return datetime.datetime.fromisoformat(roll.last_roll_timestamp)
        return None


def can_roll(user_id: int, chat_id: str) -> bool:
    """Check if a user can roll (24 hours since last roll) within a chat."""
    last_roll_time = get_last_roll_time(user_id, chat_id)
    if last_roll_time is None:
        return True

    time_since_last_roll = datetime.datetime.now() - last_roll_time
    return time_since_last_roll.total_seconds() >= 24 * 60 * 60


def record_roll(user_id: int, chat_id: str) -> None:
    """Record a user's roll timestamp for a specific chat."""
    now = datetime.datetime.now().isoformat()
    with get_session(commit=True) as session:
        roll = (
            session.query(UserRollModel)
            .filter(
                UserRollModel.user_id == user_id,
                UserRollModel.chat_id == str(chat_id),
            )
            .first()
        )

        if roll:
            roll.last_roll_timestamp = now
        else:
            roll = UserRollModel(
                user_id=user_id,
                chat_id=str(chat_id),
                last_roll_timestamp=now,
            )
            session.add(roll)
