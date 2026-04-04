"""Notification repository — data access for roll notifications.

Handles CRUD operations for the roll_notifications table, including
upserting notifications on roll, querying pending/future unsent
notifications, and atomically claiming notifications with row-level locking.
"""

from __future__ import annotations

import datetime
import logging
from datetime import timezone
from typing import List

from sqlalchemy import and_, update
from sqlalchemy.orm import Session

from utils.models import RollNotificationModel
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session(commit=True)
def upsert_notification(
    user_id: int,
    chat_id: str,
    notify_at: datetime.datetime,
    *,
    session: Session,
) -> None:
    """Create or update a roll notification for a user/chat pair.

    Resets sent status and attempt count on each upsert so only the
    latest roll's notification is tracked.
    """
    existing = (
        session.query(RollNotificationModel)
        .filter(
            RollNotificationModel.user_id == user_id,
            RollNotificationModel.chat_id == str(chat_id),
        )
        .first()
    )

    if existing:
        existing.notify_at = notify_at
        existing.sent = False
        existing.sent_at = None
        existing.attempt_count = 0
        existing.last_error = None
    else:
        notification = RollNotificationModel(
            user_id=user_id,
            chat_id=str(chat_id),
            notify_at=notify_at,
            sent=False,
            attempt_count=0,
        )
        session.add(notification)


def claim_notification(
    user_id: int,
    chat_id: str,
    expected_notify_at: datetime.datetime,
    *,
    session: Session,
) -> bool:
    """Atomically lock and mark a notification as sent.

    Uses SELECT ... FOR UPDATE to prevent concurrent workers from both
    claiming the same notification. Filters on notify_at to guard
    against stale jobs.

    Must be called within an existing session/transaction (no decorator).
    Returns True if claimed, False if not found / already sent / stale.
    """
    notification = (
        session.query(RollNotificationModel)
        .filter(
            RollNotificationModel.user_id == user_id,
            RollNotificationModel.chat_id == str(chat_id),
            RollNotificationModel.sent == False,  # noqa: E712
            RollNotificationModel.notify_at == expected_notify_at,
        )
        .with_for_update()
        .first()
    )

    if notification is None:
        return False

    notification.sent = True
    notification.sent_at = datetime.datetime.now(timezone.utc)
    return True


@with_session(commit=True)
def mark_completed(
    user_id: int,
    chat_id: str,
    expected_notify_at: datetime.datetime,
    *,
    session: Session,
) -> None:
    """Mark a notification as sent (version-guarded).

    Used when the DM was sent but claim_notification was not used
    (e.g., marking Forbidden/blocked users as complete).
    """
    session.execute(
        update(RollNotificationModel)
        .where(
            RollNotificationModel.user_id == user_id,
            RollNotificationModel.chat_id == str(chat_id),
            RollNotificationModel.sent == False,  # noqa: E712
            RollNotificationModel.notify_at == expected_notify_at,
        )
        .values(sent=True, sent_at=datetime.datetime.now(timezone.utc))
    )


@with_session
def get_all_unsent_overdue(
    *, session: Session,
) -> List[RollNotificationModel]:
    """Get all unsent notifications that are due (notify_at <= now)."""
    now = datetime.datetime.now(timezone.utc)

    return (
        session.query(RollNotificationModel)
        .filter(
            RollNotificationModel.sent == False,  # noqa: E712
            RollNotificationModel.notify_at <= now,
        )
        .all()
    )


@with_session
def get_all_unsent_future(
    *, session: Session,
) -> List[RollNotificationModel]:
    """Get all unsent notifications scheduled for the future."""
    now = datetime.datetime.now(timezone.utc)

    return (
        session.query(RollNotificationModel)
        .filter(
            RollNotificationModel.sent == False,  # noqa: E712
            RollNotificationModel.notify_at > now,
        )
        .all()
    )


@with_session(commit=True)
def mark_failed(
    user_id: int,
    chat_id: str,
    expected_notify_at: datetime.datetime,
    error: str,
    *,
    session: Session,
) -> None:
    """Record a failed notification attempt (version-guarded).

    Filters on notify_at so stale jobs can't poison newer rows.
    """
    session.execute(
        update(RollNotificationModel)
        .where(
            RollNotificationModel.user_id == user_id,
            RollNotificationModel.chat_id == str(chat_id),
            RollNotificationModel.sent == False,  # noqa: E712
            RollNotificationModel.notify_at == expected_notify_at,
        )
        .values(
            attempt_count=RollNotificationModel.attempt_count + 1,
            last_error=error,
        )
    )
