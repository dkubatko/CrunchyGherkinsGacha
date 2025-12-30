"""Achievement service for managing achievements and user unlocks.

This module provides functions for registering achievements, checking
if users have earned achievements, and granting achievements.

Usage:
    from utils.services import achievement_service

    # Register a new achievement
    achievement_service.register_achievement("Spinner", "Spend 100 spins", icon_b64)

    # Check if user has achievement
    has_it = achievement_service.has_achievement(user_id, "Spinner")

    # Grant achievement to user
    achievement_service.grant_achievement(user_id, "Spinner")
"""

from __future__ import annotations

import datetime
import logging
from typing import List, Optional

from utils.models import AchievementModel, UserAchievementModel
from utils.schemas import Achievement, UserAchievement
from utils.session import get_session

logger = logging.getLogger(__name__)


def get_achievement_by_name(name: str) -> Optional[Achievement]:
    """
    Get an achievement by its name.

    Args:
        name: The unique name of the achievement.

    Returns:
        Achievement schema if found, None otherwise.
    """
    with get_session() as session:
        achievement = session.query(AchievementModel).filter(AchievementModel.name == name).first()
        if achievement:
            return Achievement.from_orm(achievement)
        return None


def get_achievement_by_id(achievement_id: int) -> Optional[Achievement]:
    """
    Get an achievement by its ID.

    Args:
        achievement_id: The ID of the achievement.

    Returns:
        Achievement schema if found, None otherwise.
    """
    with get_session() as session:
        achievement = (
            session.query(AchievementModel).filter(AchievementModel.id == achievement_id).first()
        )
        if achievement:
            return Achievement.from_orm(achievement)
        return None


def get_all_achievements() -> List[Achievement]:
    """
    Get all registered achievements.

    Returns:
        List of Achievement schemas.
    """
    with get_session() as session:
        achievements = session.query(AchievementModel).all()
        return [Achievement.from_orm(a) for a in achievements]


def register_achievement(
    name: str,
    description: str,
    icon_b64: Optional[str] = None,
) -> Achievement:
    """
    Register a new achievement in the database.

    If an achievement with the same name already exists, returns the existing one.

    Args:
        name: Unique name for the achievement.
        description: Human-readable description of how to earn it.
        icon_b64: Optional base64-encoded icon image.

    Returns:
        The created or existing Achievement schema.
    """
    with get_session(commit=True) as session:
        # Check if achievement already exists
        existing = session.query(AchievementModel).filter(AchievementModel.name == name).first()
        if existing:
            logger.debug("Achievement '%s' already exists with id=%d", name, existing.id)
            return Achievement.from_orm(existing)

        # Create new achievement
        achievement = AchievementModel(
            name=name,
            description=description,
            icon_b64=icon_b64,
        )
        session.add(achievement)
        session.flush()

        logger.info("Registered new achievement: '%s' (id=%d)", name, achievement.id)
        return Achievement.from_orm(achievement)


def update_achievement_icon(name: str, icon_b64: str) -> Optional[Achievement]:
    """
    Update the icon for an existing achievement.

    Args:
        name: The name of the achievement to update.
        icon_b64: The new base64-encoded icon image.

    Returns:
        Updated Achievement schema if found, None otherwise.
    """
    with get_session(commit=True) as session:
        achievement = session.query(AchievementModel).filter(AchievementModel.name == name).first()
        if not achievement:
            logger.warning("Achievement '%s' not found for icon update", name)
            return None

        achievement.icon_b64 = icon_b64
        session.flush()

        logger.info("Updated icon for achievement '%s'", name)
        return Achievement.from_orm(achievement)


def has_achievement(user_id: int, achievement_name: str) -> bool:
    """
    Check if a user has earned a specific achievement.

    Args:
        user_id: The user's ID.
        achievement_name: The name of the achievement.

    Returns:
        True if the user has the achievement, False otherwise.
    """
    with get_session() as session:
        # Get achievement ID
        achievement = (
            session.query(AchievementModel)
            .filter(AchievementModel.name == achievement_name)
            .first()
        )
        if not achievement:
            return False

        # Check if user has it
        user_achievement = (
            session.query(UserAchievementModel)
            .filter(
                UserAchievementModel.user_id == user_id,
                UserAchievementModel.achievement_id == achievement.id,
            )
            .first()
        )
        return user_achievement is not None


def grant_achievement(user_id: int, achievement_name: str) -> Optional[UserAchievement]:
    """
    Grant an achievement to a user.

    This is idempotent - if the user already has the achievement, returns None.

    Args:
        user_id: The user's ID.
        achievement_name: The name of the achievement to grant.

    Returns:
        UserAchievement schema if newly granted, None if already had or achievement not found.
    """
    with get_session(commit=True) as session:
        # Get achievement
        achievement = (
            session.query(AchievementModel)
            .filter(AchievementModel.name == achievement_name)
            .first()
        )
        if not achievement:
            logger.warning("Cannot grant achievement '%s': not found", achievement_name)
            return None

        # Check if already has it
        existing = (
            session.query(UserAchievementModel)
            .filter(
                UserAchievementModel.user_id == user_id,
                UserAchievementModel.achievement_id == achievement.id,
            )
            .first()
        )
        if existing:
            logger.debug("User %d already has achievement '%s'", user_id, achievement_name)
            return None

        # Grant the achievement
        user_achievement = UserAchievementModel(
            user_id=user_id,
            achievement_id=achievement.id,
            unlocked_at=datetime.datetime.now(datetime.timezone.utc),
        )
        session.add(user_achievement)
        session.flush()

        # Reload with relationship for return
        session.refresh(user_achievement)

        logger.info(
            "Granted achievement '%s' (id=%d) to user %d",
            achievement_name,
            achievement.id,
            user_id,
        )
        return UserAchievement.from_orm(user_achievement)


def get_user_achievements(user_id: int) -> List[UserAchievement]:
    """
    Get all achievements earned by a user.

    Args:
        user_id: The user's ID.

    Returns:
        List of UserAchievement schemas with achievement details.
    """
    with get_session() as session:
        user_achievements = (
            session.query(UserAchievementModel)
            .filter(UserAchievementModel.user_id == user_id)
            .order_by(UserAchievementModel.unlocked_at.desc())
            .all()
        )
        return [UserAchievement.from_orm(ua) for ua in user_achievements]


def get_achievement_holders(achievement_name: str) -> List[int]:
    """
    Get all user IDs who have earned a specific achievement.

    Args:
        achievement_name: The name of the achievement.

    Returns:
        List of user IDs.
    """
    with get_session() as session:
        achievement = (
            session.query(AchievementModel)
            .filter(AchievementModel.name == achievement_name)
            .first()
        )
        if not achievement:
            return []

        user_achievements = (
            session.query(UserAchievementModel)
            .filter(UserAchievementModel.achievement_id == achievement.id)
            .all()
        )
        return [ua.user_id for ua in user_achievements]
