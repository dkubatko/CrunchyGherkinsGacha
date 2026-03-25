"""Achievement system with base class pattern.

This module provides the achievement engine that listens to events and grants
achievements when conditions are met. Each achievement is defined as a class
extending BaseAchievement with its own check_condition method.

Usage:
    from utils.achievements import init_achievements

    # Call once at startup (in both bot and API)
    init_achievements()

The engine subscribes to event_service and processes events automatically.

NOTE: All v1 achievements were removed as part of the Gacha 2.0 migration.
The infrastructure is kept intact for future achievement definitions.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, TYPE_CHECKING

from utils.events import (
    EventType,
)
from managers import achievement_manager
from managers import event_manager
from utils.schemas import Event, UserAchievement

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Track initialization to prevent double-subscription
_initialized = False
_init_lock = threading.Lock()


class BaseAchievement(ABC):
    """Base class for all achievements.

    Each achievement must define:
    - id: Fixed database ID for this achievement (must be unique and never change)
    - name: Unique identifier for the achievement
    - description: Human-readable description
    - check_condition: Method that returns True if the user qualifies

    The id is the source of truth for syncing with the database. If name or
    description change in code, the database entry will be updated to match.
    """

    @property
    @abstractmethod
    def id(self) -> int:
        """Fixed database ID for this achievement. Must be unique and never change."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the achievement."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of how to earn this achievement."""
        pass

    @abstractmethod
    def check_condition(self, user_id: int, event: Event) -> bool:
        """
        Check if the user meets the condition for this achievement.

        Args:
            user_id: The user to check.
            event: The event that triggered this check.

        Returns:
            True if the user qualifies for this achievement.
        """
        pass


# ============================================================================
# Achievement Mappings
# ============================================================================
# Map event types to the achievements that should be checked when that event fires.
# Add new achievements to the appropriate list based on which events trigger them.
#
# NOTE: All v1 achievement mappings were cleared during Gacha 2.0 migration.
# New achievements will be added in a future update.

# Master mapping from EventType to achievement instances
EVENT_ACHIEVEMENTS: Dict[EventType, List[BaseAchievement]] = {}


# ============================================================================
# Event Processing
# ============================================================================


def _process_event(event: Event) -> None:
    """
    Process an event and check/grant relevant achievements.

    This is called synchronously by the event_service observer pattern.
    For each matching achievement, checks the condition and grants if met.

    Args:
        event: The event that was just logged.
    """
    try:
        # Get event type enum from string
        try:
            event_type = EventType(event.event_type)
        except ValueError:
            logger.debug("Unknown event type: %s", event.event_type)
            return

        # Get achievements to check for this event type
        achievements = EVENT_ACHIEVEMENTS.get(event_type)
        if not achievements:
            return

        user_id = event.user_id

        for achievement in achievements:
            try:
                # Skip if user already has this achievement
                if achievement_manager.has_achievement(user_id, achievement.name):
                    continue

                # Check if condition is met
                if achievement.check_condition(user_id, event):
                    # Grant the achievement
                    user_achievement = achievement_manager.grant_achievement(
                        user_id, achievement.name
                    )

                    if user_achievement:
                        logger.info(
                            "Achievement unlocked: user=%d earned '%s'",
                            user_id,
                            achievement.name,
                        )
                        # Queue notification (non-blocking)
                        _queue_achievement_notification(user_id, event.chat_id, user_achievement)

            except Exception as e:
                logger.error(
                    "Error checking achievement '%s' for user %d: %s",
                    achievement.name,
                    user_id,
                    e,
                    exc_info=True,
                )

    except Exception as e:
        logger.error("Error processing event for achievements: %s", e, exc_info=True)


def _queue_achievement_notification(
    user_id: int, chat_id: str, user_achievement: UserAchievement
) -> None:
    """
    Queue a notification to be sent about the achievement unlock.

    This is non-blocking and schedules the notification in the background.

    Args:
        user_id: The user who earned the achievement.
        chat_id: The chat where the event occurred.
        user_achievement: The achievement that was unlocked.
    """
    try:
        # Import here to avoid circular imports
        from api.background_tasks import send_achievement_notification

        # Schedule the notification asynchronously
        # Try to get the running event loop, create task if available
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_achievement_notification(user_id, chat_id, user_achievement))
        except RuntimeError:
            # No running event loop - we're in a sync context
            # Create a new thread to run the async notification
            def run_notification():
                asyncio.run(send_achievement_notification(user_id, chat_id, user_achievement))

            thread = threading.Thread(target=run_notification, daemon=True)
            thread.start()

    except ImportError:
        logger.warning("background_tasks not available, skipping notification")
    except Exception as e:
        logger.error("Failed to queue achievement notification: %s", e)


# ============================================================================
# Initialization
# ============================================================================


def init_achievements() -> None:
    """
    Initialize the achievement system by subscribing to events.

    This should be called once at startup from both bot and API.
    It's safe to call multiple times - subsequent calls are no-ops.
    """
    global _initialized

    with _init_lock:
        if _initialized:
            logger.debug("Achievement system already initialized")
            return

        # Subscribe to event notifications
        event_manager.subscribe(_process_event)
        _initialized = True


def ensure_achievements_registered() -> None:
    """
    Ensure all achievement definitions are synced with the database.

    This should be called after database migrations have run.
    It creates new achievements and updates existing ones if name/description changed.
    Achievements are synced by their fixed ID, making renames safe.
    """
    # Collect unique achievements by ID (same achievement may appear under multiple event types)
    unique_achievements: dict[int, BaseAchievement] = {}
    for achievements in EVENT_ACHIEVEMENTS.values():
        for achievement in achievements:
            if achievement.id in unique_achievements:
                # Verify no ID conflicts
                existing = unique_achievements[achievement.id]
                if existing.name != achievement.name:
                    logger.error(
                        "Achievement ID conflict: id=%d used by both '%s' and '%s'",
                        achievement.id,
                        existing.name,
                        achievement.name,
                    )
            unique_achievements[achievement.id] = achievement

    created_count = 0
    updated_count = 0
    for achievement in unique_achievements.values():
        result = achievement_manager.sync_achievement(
            achievement_id=achievement.id,
            name=achievement.name,
            description=achievement.description,
        )
        if result == "created":
            logger.debug("Created new achievement: '%s' (id=%d)", achievement.name, achievement.id)
            created_count += 1
        elif result == "updated":
            logger.debug("Updated achievement: '%s' (id=%d)", achievement.name, achievement.id)
            updated_count += 1

    logger.info(
        "Synced %d achievements across %d event types (%d created, %d updated)",
        len(unique_achievements),
        len(EVENT_ACHIEVEMENTS),
        created_count,
        updated_count,
    )
