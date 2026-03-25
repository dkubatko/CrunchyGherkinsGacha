"""Achievement manager — achievement granting logic.

Handles syncing achievement definitions, checking user achievement
status, and granting achievements with conditional DB lookups.
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from repos import achievement_repo
from utils.schemas import UserAchievement
from utils.session import get_session

logger = logging.getLogger(__name__)


def sync_achievement(
    achievement_id: int,
    name: str,
    description: str,
) -> Literal["created", "updated", "unchanged"]:
    """
    Sync an achievement definition with the database by ID.

    This is the preferred way to ensure achievements exist and stay in sync.
    The ID is the source of truth - if an achievement with this ID exists,
    its name and description will be updated to match the code definition.

    Returns:
        "created" if a new achievement was added,
        "updated" if an existing achievement was modified,
        "unchanged" if no changes were needed.
    """
    achievement, status, old_name, old_desc = achievement_repo.upsert_achievement_by_id(achievement_id, name, description)

    if status == "created":
        logger.info("Created new achievement: '%s' (id=%d)", name, achievement_id)
    elif status == "updated":
        logger.info(
            "Updated achievement id=%d: name '%s'->'%s', description '%s'->'%s'",
            achievement_id,
            old_name,
            name,
            old_desc,
            description,
        )

    return status


def has_achievement(user_id: int, achievement_name: str) -> bool:
    """
    Check if a user has earned a specific achievement.

    Uses a single session to atomically look up the achievement by name
    and check the user's unlock status.

    Args:
        user_id: The user's ID.
        achievement_name: The name of the achievement.

    Returns:
        True if the user has the achievement, False otherwise.
    """
    with get_session() as session:
        achievement = achievement_repo.get_achievement_model_by_name(achievement_name, session=session)
        if not achievement:
            return False
        return achievement_repo.get_user_achievement(user_id, achievement.id, session=session) is not None


def grant_achievement(user_id: int, achievement_name: str) -> Optional[UserAchievement]:
    """
    Grant an achievement to a user.

    Uses a single session to atomically look up, check, and grant the
    achievement.  This is idempotent — if the user already has the
    achievement, returns None.

    Args:
        user_id: The user's ID.
        achievement_name: The name of the achievement to grant.

    Returns:
        UserAchievement schema if newly granted, None if already had or achievement not found.
    """
    with get_session(commit=True) as session:
        achievement = achievement_repo.get_achievement_model_by_name(achievement_name, session=session)
        if not achievement:
            logger.warning("Cannot grant achievement '%s': not found", achievement_name)
            return None

        existing = achievement_repo.get_user_achievement(user_id, achievement.id, session=session)
        if existing:
            logger.debug("User %d already has achievement '%s'", user_id, achievement_name)
            return None

        result = achievement_repo.create_user_achievement(user_id, achievement.id, session=session)

    logger.info("Granted achievement '%s' to user %d", achievement_name, user_id)
    return result
