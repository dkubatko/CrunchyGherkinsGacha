"""Thread repository for managing chat thread IDs.

This module provides all thread-related data access operations including
getting, setting, and clearing thread IDs for chats.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from utils.models import ThreadModel
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session
def get_thread_id(chat_id: str, type: str = "main", *, session: Session) -> Optional[int]:
    """Get the thread_id for a chat_id and type, or None if not set.

    Args:
        chat_id: The chat ID to query.
        type: The thread type ('main' or 'trade'). Defaults to 'main'.
    """
    thread = (
        session.query(ThreadModel)
        .filter(
            ThreadModel.chat_id == str(chat_id),
            ThreadModel.type == type,
        )
        .first()
    )
    return thread.thread_id if thread else None


@with_session(commit=True)
def set_thread_id(chat_id: str, thread_id: int, type: str = "main", *, session: Session) -> bool:
    """Set the thread_id for a chat_id and type. Returns True if successful.

    Args:
        chat_id: The chat ID to set.
        thread_id: The thread ID to set.
        type: The thread type ('main' or 'trade'). Defaults to 'main'.
    """
    # Try to find existing thread
    existing = (
        session.query(ThreadModel)
        .filter(
            ThreadModel.chat_id == str(chat_id),
            ThreadModel.type == type,
        )
        .first()
    )

    if existing:
        existing.thread_id = thread_id
    else:
        new_thread = ThreadModel(
            chat_id=str(chat_id),
            thread_id=thread_id,
            type=type,
        )
        session.add(new_thread)
    return True


@with_session(commit=True)
def clear_thread_ids(chat_id: str, *, session: Session) -> bool:
    """Clear all thread_ids for a chat_id. Returns True if successful.

    Args:
        chat_id: The chat ID to clear threads for.
    """
    deleted = (
        session.query(ThreadModel)
        .filter(
            ThreadModel.chat_id == str(chat_id),
        )
        .delete()
    )
    return deleted > 0
