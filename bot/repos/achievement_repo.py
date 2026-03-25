"""Achievement repository for database access to achievements and user unlocks.

This module provides data access functions for registering achievements,
querying achievement records, and managing user achievement associations.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from utils.models import AchievementModel, UserAchievementModel
from utils.schemas import Achievement, UserAchievement
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session
def get_achievement_model_by_id(achievement_id: int, *, session: Session) -> Optional[Achievement]:
    """Fetch a raw AchievementModel by primary key (for manager use)."""
    result = (
        session.query(AchievementModel)
        .filter(AchievementModel.id == achievement_id)
        .first()
    )
    return Achievement.from_orm(result) if result else None


@with_session
def get_achievement_model_by_name(name: str, *, session: Session) -> Optional[Achievement]:
    """Fetch a raw AchievementModel by name (for manager use)."""
    result = session.query(AchievementModel).filter(AchievementModel.name == name).first()
    return Achievement.from_orm(result) if result else None


@with_session(commit=True)
def upsert_achievement_by_id(
    achievement_id: int, name: str, description: str, *, session: Session
) -> tuple[Achievement, str, Optional[str], Optional[str]]:
    """Insert or update an achievement by its fixed ID.

    Returns ``(model, status, old_name, old_description)`` where status is
    ``'created'``, ``'updated'``, or ``'unchanged'``.
    ``old_name`` and ``old_description`` are only set when status is ``'updated'``.
    """
    existing = (
        session.query(AchievementModel)
        .filter(AchievementModel.id == achievement_id)
        .first()
    )
    if existing:
        if existing.name == name and existing.description == description:
            return Achievement.from_orm(existing), "unchanged", None, None
        old_name = existing.name
        old_desc = existing.description
        existing.name = name
        existing.description = description
        session.flush()
        return Achievement.from_orm(existing), "updated", old_name, old_desc

    achievement = AchievementModel(
        id=achievement_id, name=name, description=description, icon=None
    )
    session.add(achievement)
    session.flush()
    return Achievement.from_orm(achievement), "created", None, None


@with_session
def get_user_achievement(user_id: int, achievement_id: int, *, session: Session) -> Optional[UserAchievement]:
    """Check if a user has a specific achievement by achievement ID."""
    result = (
        session.query(UserAchievementModel)
        .options(joinedload(UserAchievementModel.achievement))
        .filter(
            UserAchievementModel.user_id == user_id,
            UserAchievementModel.achievement_id == achievement_id,
        )
        .first()
    )
    return UserAchievement.from_orm(result) if result else None


@with_session(commit=True)
def create_user_achievement(user_id: int, achievement_id: int, *, session: Session) -> UserAchievement:
    """Grant an achievement to a user. Returns the created UserAchievement."""
    import datetime

    user_achievement = UserAchievementModel(
        user_id=user_id,
        achievement_id=achievement_id,
        unlocked_at=datetime.datetime.now(datetime.timezone.utc),
    )
    session.add(user_achievement)
    session.flush()
    # Re-fetch with eager-loaded relationship for the DTO
    user_achievement = (
        session.query(UserAchievementModel)
        .options(joinedload(UserAchievementModel.achievement))
        .filter(UserAchievementModel.id == user_achievement.id)
        .one()
    )
    return UserAchievement.from_orm(user_achievement)


@with_session
def get_achievement_by_name(name: str, *, session: Session) -> Optional[Achievement]:
    """
    Get an achievement by its name.

    Args:
        name: The unique name of the achievement.

    Returns:
        Achievement if found, None otherwise.
    """
    result = session.query(AchievementModel).filter(AchievementModel.name == name).first()
    return Achievement.from_orm(result) if result else None


@with_session
def get_achievement_by_id(achievement_id: int, *, session: Session) -> Optional[Achievement]:
    """
    Get an achievement by its ID.

    Args:
        achievement_id: The ID of the achievement.

    Returns:
        Achievement if found, None otherwise.
    """
    result = (
        session.query(AchievementModel).filter(AchievementModel.id == achievement_id).first()
    )
    return Achievement.from_orm(result) if result else None


@with_session
def get_all_achievements(*, session: Session) -> List[Achievement]:
    """
    Get all registered achievements.

    Returns:
        List of Achievement instances.
    """
    results = session.query(AchievementModel).all()
    return [Achievement.from_orm(r) for r in results]


@with_session(commit=True)
def register_achievement(
    name: str,
    description: str,
    icon_b64: Optional[str] = None,
    *,
    session: Session,
) -> Achievement:
    """
    Register a new achievement in the database.

    If an achievement with the same name already exists, returns the existing one.

    Args:
        name: Unique name for the achievement.
        description: Human-readable description of how to earn it.
        icon_b64: Optional base64-encoded icon image.

    Returns:
        The created or existing Achievement.
    """
    import base64

    # Check if achievement already exists
    existing = session.query(AchievementModel).filter(AchievementModel.name == name).first()
    if existing:
        logger.debug("Achievement '%s' already exists with id=%d", name, existing.id)
        return Achievement.from_orm(existing)

    # Create new achievement
    icon_bytes = base64.b64decode(icon_b64) if icon_b64 else None
    achievement = AchievementModel(
        name=name,
        description=description,
        icon=icon_bytes,
    )
    session.add(achievement)
    session.flush()

    logger.info("Registered new achievement: '%s' (id=%d)", name, achievement.id)
    return Achievement.from_orm(achievement)


@with_session(commit=True)
def update_achievement_icon(name: str, icon_b64: str, *, session: Session) -> Optional[Achievement]:
    """
    Update the icon for an existing achievement.

    Args:
        name: The name of the achievement to update.
        icon_b64: The new base64-encoded icon image.

    Returns:
        Updated Achievement if found, None otherwise.
    """
    import base64

    achievement = session.query(AchievementModel).filter(AchievementModel.name == name).first()
    if not achievement:
        logger.warning("Achievement '%s' not found for icon update", name)
        return None

    achievement.icon = base64.b64decode(icon_b64)
    session.flush()

    logger.info("Updated icon for achievement '%s'", name)
    return Achievement.from_orm(achievement)


@with_session
def get_user_achievements(user_id: int, *, session: Session) -> List[UserAchievement]:
    """
    Get all achievements earned by a user.

    Args:
        user_id: The user's ID.

    Returns:
        List of UserAchievement instances, ordered by unlock time (oldest first).
    """
    results = (
        session.query(UserAchievementModel)
        .options(joinedload(UserAchievementModel.achievement))
        .filter(UserAchievementModel.user_id == user_id)
        .order_by(UserAchievementModel.unlocked_at.asc())
        .all()
    )
    return [UserAchievement.from_orm(r) for r in results]


@with_session
def get_achievement_holders(achievement_name: str, *, session: Session) -> List[int]:
    """
    Get all user IDs who have earned a specific achievement.

    Args:
        achievement_name: The name of the achievement.

    Returns:
        List of user IDs.
    """
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
