"""Preferences repository — data access for user preferences.

Handles reading and toggling per-user settings stored in the
user_preferences table.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from utils.models import UserPreferencesModel
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session
def get_notify_rolls(user_id: int, *, session: Session) -> bool:
    """Get the notify_rolls preference for a user.

    Returns True (notifications enabled) if no preferences row exists.
    """
    prefs = (
        session.query(UserPreferencesModel)
        .filter(UserPreferencesModel.user_id == user_id)
        .first()
    )
    if prefs is None:
        return True
    return prefs.notify_rolls


@with_session(commit=True)
def toggle_notify_rolls(user_id: int, *, session: Session) -> bool:
    """Toggle the notify_rolls preference for a user.

    Creates a preferences row if one doesn't exist (defaults to True,
    so first toggle sets it to False).

    Returns the new state after toggling.
    """
    prefs = (
        session.query(UserPreferencesModel)
        .filter(UserPreferencesModel.user_id == user_id)
        .first()
    )

    if prefs is None:
        # First toggle: default is True, so set to False
        prefs = UserPreferencesModel(user_id=user_id, notify_rolls=False)
        session.add(prefs)
        return False
    else:
        prefs.notify_rolls = not prefs.notify_rolls
        return prefs.notify_rolls
