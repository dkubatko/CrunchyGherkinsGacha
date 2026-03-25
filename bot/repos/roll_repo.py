"""Roll repository for tracking user roll timestamps.

This module provides data access operations for roll timestamps
including retrieving last roll time and recording new rolls.
"""

from __future__ import annotations

import datetime
import logging
from datetime import timezone
from typing import Optional

from sqlalchemy.orm import Session

from utils.models import UserRollModel
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session
def get_last_roll_time(user_id: int, chat_id: str, *, session: Session) -> Optional[datetime.datetime]:
    """Get the last roll timestamp for a user within a specific chat.

    Returns a timezone-aware datetime in UTC.
    """
    roll = (
        session.query(UserRollModel)
        .filter(
            UserRollModel.user_id == user_id,
            UserRollModel.chat_id == str(chat_id),
        )
        .first()
    )
    if roll and roll.last_roll_timestamp:
        dt = roll.last_roll_timestamp
        # If the datetime is naive, assume it's UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return None


@with_session(commit=True)
def record_roll(user_id: int, chat_id: str, *, session: Session) -> None:
    """Record a user's roll timestamp for a specific chat."""
    now = datetime.datetime.now(timezone.utc)
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
