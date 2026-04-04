"""Notification manager — business logic for roll notifications.

Orchestrates notification persistence and querying. This module is
PTB-free (no telegram imports) — all Telegram Bot API interactions
live in handlers/notifications.py.
"""

from __future__ import annotations

import datetime
import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from repos import notification_repo, preferences_repo, user_repo
from utils.models import RollNotificationModel
from utils.session import get_session

logger = logging.getLogger(__name__)


def persist_notification(
    user_id: int,
    chat_id: str,
    notify_at: datetime.datetime,
    *,
    session: Optional[Session] = None,
) -> None:
    """Persist a roll notification record.

    When called without a session, opens its own transaction.
    Pass session= to share an existing transaction.
    """
    notification_repo.upsert_notification(
        user_id,
        chat_id,
        notify_at,
        session=session,
    )


def claim_and_complete(
    user_id: int,
    chat_id: str,
    expected_notify_at: datetime.datetime,
) -> bool:
    """Check deliverability and atomically claim a notification.

    Business logic checks (enrollment, preferences) run first, then
    the repo's row-level lock claim prevents duplicate sends.

    Returns True if claimed and marked sent, False otherwise.
    """
    with get_session(commit=True) as session:
        # Business logic: is user still enrolled in this chat?
        if not user_repo.is_user_in_chat(chat_id, user_id, session=session):
            return False

        # Business logic: has user opted out of roll notifications?
        if not preferences_repo.get_notify_rolls(user_id, session=session):
            return False

        # Atomic claim with row lock (pure data access)
        return notification_repo.claim_notification(
            user_id, chat_id, expected_notify_at, session=session,
        )


def mark_completed(
    user_id: int,
    chat_id: str,
    expected_notify_at: datetime.datetime,
) -> None:
    """Mark a notification as sent (version-guarded, no deliverability check).

    Used for cases like user blocked bot — mark as done without re-checking.
    """
    notification_repo.mark_completed(user_id, chat_id, expected_notify_at)


def get_all_unsent_overdue() -> List[RollNotificationModel]:
    """Get all overdue unsent notification rows (no prefs/enrollment filter)."""
    return notification_repo.get_all_unsent_overdue()


def get_all_unsent_future() -> List[RollNotificationModel]:
    """Get all future unsent notification rows (no prefs/enrollment filter)."""
    return notification_repo.get_all_unsent_future()


def fail_notification(
    user_id: int,
    chat_id: str,
    expected_notify_at: datetime.datetime,
    error: str,
) -> None:
    """Record a failed notification attempt (version-guarded)."""
    notification_repo.mark_failed(user_id, chat_id, expected_notify_at, error)
