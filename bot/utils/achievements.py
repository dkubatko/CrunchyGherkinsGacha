"""Achievement system with base class pattern.

This module provides the achievement engine that listens to events and grants
achievements when conditions are met. Each achievement is defined as a class
extending BaseAchievement with its own check_condition method.

Usage:
    from utils.achievements import init_achievements

    # Call once at startup (in both bot and API)
    init_achievements()

The engine subscribes to event_service and processes events automatically.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, TYPE_CHECKING

from utils.events import (
    EventType,
    SpinOutcome,
    ClaimOutcome,
    CreateOutcome,
    MegaspinOutcome,
    MinesweeperOutcome,
    BurnOutcome,
    RollOutcome,
    RtbOutcome,
)
from utils.services import achievement_service, event_service
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


class SpinnerAchievement(BaseAchievement):
    """Achievement for spending spins."""

    REQUIRED_SPINS = 1000

    @property
    def id(self) -> int:
        return 1

    @property
    def name(self) -> str:
        return "Spinner"

    @property
    def description(self) -> str:
        return f"Spend {self.REQUIRED_SPINS} spins"

    def check_condition(self, user_id: int, event: Event) -> bool:
        """Check if user has spent 100 spins (actual spins, not errors)."""
        # Count only actual spin outcomes (not NO_SPINS or ERROR)
        actual_spin_outcomes = [
            SpinOutcome.CARD_WIN,
            SpinOutcome.CLAIM_WIN,
            SpinOutcome.LOSS,
        ]

        total_spins = 0
        for outcome in actual_spin_outcomes:
            total_spins += event_service.count_events(
                user_id=user_id,
                event_type=EventType.SPIN,
                outcome=outcome,
            )
        return total_spins >= self.REQUIRED_SPINS


class CollectorAchievement(BaseAchievement):
    """Achievement for collecting 100 cards."""

    REQUIRED_CARDS = 100

    # Only check on outcomes that actually add cards to collection
    VALID_OUTCOMES = {
        EventType.CLAIM: {ClaimOutcome.SUCCESS.value},
        EventType.SPIN: {SpinOutcome.CARD_WIN.value},
        EventType.MEGASPIN: {MegaspinOutcome.SUCCESS.value},
        EventType.MINESWEEPER: {MinesweeperOutcome.WON.value},
    }

    @property
    def id(self) -> int:
        return 2

    @property
    def name(self) -> str:
        return "Collector"

    @property
    def description(self) -> str:
        return f"Collect {self.REQUIRED_CARDS} cards"

    def check_condition(self, user_id: int, event: Event) -> bool:
        """Check if user has 100+ cards in their collection."""
        # Only check on outcomes that add cards
        try:
            event_type = EventType(event.event_type)
        except ValueError:
            return False

        valid_outcomes = self.VALID_OUTCOMES.get(event_type)
        if valid_outcomes is None or event.outcome not in valid_outcomes:
            return False

        # Count user's total cards across all chats
        from utils.services import card_service

        total_cards = card_service.get_user_card_count(user_id)
        return total_cards >= self.REQUIRED_CARDS


class CreatorAchievement(BaseAchievement):
    """Achievement for creating a unique card."""

    @property
    def id(self) -> int:
        return 3

    @property
    def name(self) -> str:
        return "Creator"

    @property
    def description(self) -> str:
        return "Create a Unique card"

    def check_condition(self, user_id: int, event: Event) -> bool:
        """Check if user just created a unique card."""
        # Only grant on successful unique card creation
        return (
            event.event_type == EventType.CREATE.value
            and event.outcome == CreateOutcome.SUCCESS.value
        )


class ThiefAchievement(BaseAchievement):
    """Achievement for stealing someone else's roll."""

    @property
    def id(self) -> int:
        return 4

    @property
    def name(self) -> str:
        return "Thief"

    @property
    def description(self) -> str:
        return "Steal someone else's rolled card"

    def check_condition(self, user_id: int, event: Event) -> bool:
        """Check if user claimed a card that was rolled by someone else."""
        # Only check successful claims
        if event.event_type != EventType.CLAIM.value or event.outcome != ClaimOutcome.SUCCESS.value:
            return False

        # Need card_id to look up the rolled card
        if event.card_id is None:
            return False

        # Look up the rolled card to get the original roller
        from utils.services import rolled_card_service

        rolled_card = rolled_card_service.get_rolled_card_by_card_id(event.card_id)
        if rolled_card is None:
            return False

        # Check if the claimer is different from the original roller
        return rolled_card.original_roller_id != user_id


class MasterThiefAchievement(BaseAchievement):
    """Achievement for stealing someone else's Legendary roll."""

    @property
    def id(self) -> int:
        return 5

    @property
    def name(self) -> str:
        return "Master Thief"

    @property
    def description(self) -> str:
        return "Steal someone else's Legendary card"

    def check_condition(self, user_id: int, event: Event) -> bool:
        """Check if user claimed a Legendary card that was rolled by someone else."""
        # Only check successful claims
        if event.event_type != EventType.CLAIM.value or event.outcome != ClaimOutcome.SUCCESS.value:
            return False

        # Need card_id to look up the rolled card
        if event.card_id is None:
            return False

        # Look up the rolled card to get the original roller
        from utils.services import rolled_card_service, card_service

        rolled_card = rolled_card_service.get_rolled_card_by_card_id(event.card_id)
        if rolled_card is None:
            return False

        # Check if the claimer is different from the original roller
        if rolled_card.original_roller_id == user_id:
            return False

        # Check if the card is Legendary
        card = card_service.get_card(event.card_id)
        if card is None:
            return False

        return card.rarity == "Legendary"


class LetItBurnAchievement(BaseAchievement):
    """Achievement for burning 100 cards."""

    REQUIRED_BURNS = 100

    @property
    def id(self) -> int:
        return 6

    @property
    def name(self) -> str:
        return "Let it burn!"

    @property
    def description(self) -> str:
        return f"Burn {self.REQUIRED_BURNS} cards"

    def check_condition(self, user_id: int, event: Event) -> bool:
        """Check if user has burned 100 cards."""
        # Only check on successful burns
        if event.event_type != EventType.BURN.value or event.outcome != BurnOutcome.SUCCESS.value:
            return False

        # Count total successful burns
        total_burns = event_service.count_events(
            user_id=user_id,
            event_type=EventType.BURN,
            outcome=BurnOutcome.SUCCESS,
        )
        return total_burns >= self.REQUIRED_BURNS


class CrunchyGherkinAchievement(BaseAchievement):
    """Achievement for rolling a card in Season 1."""

    @property
    def id(self) -> int:
        return 7

    @property
    def name(self) -> str:
        return "Crunchy Gherkin"

    @property
    def description(self) -> str:
        return "Roll a card in Season 1"

    def check_condition(self, user_id: int, event: Event) -> bool:
        """Check if user rolled a card in Season 1."""
        # Any successful roll in Season 1 qualifies
        return (
            event.event_type == EventType.ROLL.value and event.outcome == RollOutcome.SUCCESS.value
        )


class HighRollerAchievement(BaseAchievement):
    """Achievement for rolling a Legendary card."""

    @property
    def id(self) -> int:
        return 8

    @property
    def name(self) -> str:
        return "High Roller"

    @property
    def description(self) -> str:
        return "Roll a Legendary card"

    def check_condition(self, user_id: int, event: Event) -> bool:
        """Check if user rolled a Legendary card."""
        # Only check successful rolls
        if event.event_type != EventType.ROLL.value or event.outcome != RollOutcome.SUCCESS.value:
            return False

        # Check rarity from event payload
        if event.payload and event.payload.get("rarity") == "Legendary":
            return True

        return False


class ChooChooBusAchievement(BaseAchievement):
    """Achievement for winning a 10x bet in Ride the Bus."""

    REQUIRED_MULTIPLIER = 10

    @property
    def id(self) -> int:
        return 9

    @property
    def name(self) -> str:
        return "Choo-choo bus"

    @property
    def description(self) -> str:
        return f"Win a {self.REQUIRED_MULTIPLIER}x bet in Ride the Bus"

    def check_condition(self, user_id: int, event: Event) -> bool:
        """Check if user won with a 10x multiplier in Ride the Bus."""
        # Only check RTB wins
        if event.event_type != EventType.RTB.value or event.outcome != RtbOutcome.WON.value:
            return False

        # Check multiplier from event payload
        if event.payload and event.payload.get("multiplier") >= self.REQUIRED_MULTIPLIER:
            return True

        return False


class BussyAchievement(BaseAchievement):
    """Achievement for cashing out a 2x in Ride the Bus."""

    REQUIRED_MULTIPLIER = 2

    @property
    def id(self) -> int:
        return 10

    @property
    def name(self) -> str:
        return "Bussy"

    @property
    def description(self) -> str:
        return f"Cash out a {self.REQUIRED_MULTIPLIER}x in Ride the Bus"

    def check_condition(self, user_id: int, event: Event) -> bool:
        """Check if user cashed out with a 2x multiplier in Ride the Bus."""
        # Only check RTB cash outs
        if event.event_type != EventType.RTB.value or event.outcome != RtbOutcome.CASHED_OUT.value:
            return False

        # Check multiplier from event payload
        if event.payload and event.payload.get("multiplier") == self.REQUIRED_MULTIPLIER:
            return True

        return False


class GreedyAchievement(BaseAchievement):
    """Achievement for losing on the last card in Ride the Bus."""

    LAST_CARD_POSITION = 4  # Position when guessing the 5th card

    @property
    def id(self) -> int:
        return 13

    @property
    def name(self) -> str:
        return "Greedy"

    @property
    def description(self) -> str:
        return "Lose on the last card in Ride the Bus"

    def check_condition(self, user_id: int, event: Event) -> bool:
        """Check if user lost on the last card in Ride the Bus."""
        if event.event_type != EventType.RTB.value or event.outcome != RtbOutcome.LOST.value:
            return False

        if event.payload and event.payload.get("current_position") == self.LAST_CARD_POSITION:
            return True

        return False


class AddictAchievement(BaseAchievement):
    """Achievement for losing 5 Ride the Bus games in a row within an hour."""

    REQUIRED_LOSSES = 5
    TIME_WINDOW_SECONDS = 3600  # 1 hour

    @property
    def id(self) -> int:
        return 11

    @property
    def name(self) -> str:
        return "Addict"

    @property
    def description(self) -> str:
        return f"Lose {self.REQUIRED_LOSSES} Ride the Bus games in a row"

    def check_condition(self, user_id: int, event: Event) -> bool:
        """Check if user has lost 5 RTB games in a row within an hour."""
        from datetime import datetime, timedelta, timezone

        # Only check on RTB losses
        if event.event_type != EventType.RTB.value or event.outcome != RtbOutcome.LOST.value:
            return False

        # Get recent RTB game-ending events for this user
        ending_outcomes = [RtbOutcome.WON.value, RtbOutcome.LOST.value, RtbOutcome.CASHED_OUT.value]
        game_endings = event_service.get_events_by_user(
            user_id=user_id,
            event_types=[EventType.RTB],
            outcomes=ending_outcomes,
            limit=self.REQUIRED_LOSSES,
        )

        # Check if we have 5 events and all are losses
        if len(game_endings) < self.REQUIRED_LOSSES:
            return False

        if not all(e.outcome == RtbOutcome.LOST.value for e in game_endings):
            return False

        # Check all losses are within the time window
        now = datetime.now(timezone.utc)
        oldest_event = game_endings[-1]
        time_diff = now - oldest_event.timestamp.replace(tzinfo=timezone.utc)

        return time_diff.total_seconds() <= self.TIME_WINDOW_SECONDS


class UnluckyAchievement(BaseAchievement):
    """Achievement for getting no cards in 100 spins."""

    REQUIRED_LOSSES = 100

    @property
    def id(self) -> int:
        return 12

    @property
    def name(self) -> str:
        return "Unlucky"

    @property
    def description(self) -> str:
        return f"Get no cards in {self.REQUIRED_LOSSES} spins"

    def check_condition(self, user_id: int, event: Event) -> bool:
        """Check if user has lost 100 spins in a row (no card wins)."""
        # Only check on spin losses
        if event.event_type != EventType.SPIN.value or event.outcome != SpinOutcome.LOSS.value:
            return False

        # Get recent spin events (only actual spins, not errors)
        actual_outcomes = [
            SpinOutcome.CARD_WIN.value,
            SpinOutcome.CLAIM_WIN.value,
            SpinOutcome.LOSS.value,
        ]
        recent_spins = event_service.get_events_by_user(
            user_id=user_id,
            event_types=[EventType.SPIN],
            outcomes=actual_outcomes,
            limit=self.REQUIRED_LOSSES,
        )

        # Check if we have 100 spins and none are card wins
        if len(recent_spins) < self.REQUIRED_LOSSES:
            return False

        return all(e.outcome != SpinOutcome.CARD_WIN.value for e in recent_spins)


# ============================================================================
# Achievement Mappings
# ============================================================================
# Map event types to the achievements that should be checked when that event fires.
# Add new achievements to the appropriate list based on which events trigger them.

SPIN_ACHIEVEMENTS: List[BaseAchievement] = [
    SpinnerAchievement(),
    CollectorAchievement(),
    UnluckyAchievement(),
]

CLAIM_ACHIEVEMENTS: List[BaseAchievement] = [
    CollectorAchievement(),
    ThiefAchievement(),
    MasterThiefAchievement(),
]

MEGASPIN_ACHIEVEMENTS: List[BaseAchievement] = [
    CollectorAchievement(),
]

MINESWEEPER_ACHIEVEMENTS: List[BaseAchievement] = [
    CollectorAchievement(),
]

CREATE_ACHIEVEMENTS: List[BaseAchievement] = [
    CreatorAchievement(),
]

BURN_ACHIEVEMENTS: List[BaseAchievement] = [
    LetItBurnAchievement(),
]

ROLL_ACHIEVEMENTS: List[BaseAchievement] = [
    CrunchyGherkinAchievement(),
    HighRollerAchievement(),
]

RTB_ACHIEVEMENTS: List[BaseAchievement] = [
    ChooChooBusAchievement(),
    BussyAchievement(),
    GreedyAchievement(),
    AddictAchievement(),
]

# Master mapping from EventType to achievement instances
EVENT_ACHIEVEMENTS: Dict[EventType, List[BaseAchievement]] = {
    EventType.SPIN: SPIN_ACHIEVEMENTS,
    EventType.CLAIM: CLAIM_ACHIEVEMENTS,
    EventType.MEGASPIN: MEGASPIN_ACHIEVEMENTS,
    EventType.MINESWEEPER: MINESWEEPER_ACHIEVEMENTS,
    EventType.CREATE: CREATE_ACHIEVEMENTS,
    EventType.BURN: BURN_ACHIEVEMENTS,
    EventType.ROLL: ROLL_ACHIEVEMENTS,
    EventType.RTB: RTB_ACHIEVEMENTS,
}


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
                if achievement_service.has_achievement(user_id, achievement.name):
                    continue

                # Check if condition is met
                if achievement.check_condition(user_id, event):
                    # Grant the achievement
                    user_achievement = achievement_service.grant_achievement(
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
        event_service.subscribe(_process_event)
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
        result = achievement_service.sync_achievement(
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
