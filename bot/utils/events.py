"""
Event types and outcomes for telemetry logging.

This module defines all valid event types and their corresponding outcome enums.
Each event type has a fixed set of valid outcomes that are validated at log time.

Usage:
    from utils.events import EventType, RollOutcome

    event_service.log(
        EventType.ROLL,
        RollOutcome.SUCCESS,
        user_id=123,
        chat_id="-100123456",
        card_id=456,
        rarity="legendary",
        source_type="user",
    )

To add new outcomes: Add to the relevant outcome enum.
To add new event types: Add to EventType and create corresponding outcome enum,
then add mapping to VALID_OUTCOMES.
"""

from enum import Enum
from typing import Dict, Type


class EventType(str, Enum):
    """All event types that can be logged."""

    ROLL = "ROLL"
    REROLL = "REROLL"
    CLAIM = "CLAIM"
    TRADE = "TRADE"
    LOCK = "LOCK"
    ROLL_LOCK = "ROLL_LOCK"
    BURN = "BURN"
    REFRESH = "REFRESH"
    RECYCLE = "RECYCLE"
    CREATE = "CREATE"
    SPIN = "SPIN"
    MEGASPIN = "MEGASPIN"
    MINESWEEPER = "MINESWEEPER"
    RTB = "RTB"


# --- Outcome enums per event type ---


class RollOutcome(str, Enum):
    """Outcomes for ROLL events."""

    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class RerollOutcome(str, Enum):
    """Outcomes for REROLL events."""

    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class ClaimOutcome(str, Enum):
    """Outcomes for CLAIM events."""

    SUCCESS = "SUCCESS"
    ALREADY_OWNED = "ALREADY_OWNED"  # User already owns this card
    TAKEN = "TAKEN"  # Someone else claimed it
    INSUFFICIENT = "INSUFFICIENT"  # Not enough claim points
    ERROR = "ERROR"


class TradeOutcome(str, Enum):
    """Outcomes for TRADE events."""

    CREATED = "CREATED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class LockOutcome(str, Enum):
    """Outcomes for LOCK events (collection locks)."""

    LOCKED = "LOCKED"
    UNLOCKED = "UNLOCKED"
    INSUFFICIENT = "INSUFFICIENT"  # Not enough claim points for lock
    ERROR = "ERROR"


class RollLockOutcome(str, Enum):
    """Outcomes for ROLL_LOCK events (rolled card locks to prevent reroll)."""

    LOCKED = "LOCKED"
    INSUFFICIENT = "INSUFFICIENT"  # Not enough claim points for lock
    ERROR = "ERROR"


class BurnOutcome(str, Enum):
    """Outcomes for BURN events."""

    SUCCESS = "SUCCESS"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class RefreshOutcome(str, Enum):
    """Outcomes for REFRESH events."""

    SUCCESS = "SUCCESS"
    KEPT = "KEPT"  # User kept original image
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class RecycleOutcome(str, Enum):
    """Outcomes for RECYCLE events."""

    SUCCESS = "SUCCESS"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class CreateOutcome(str, Enum):
    """Outcomes for CREATE (unique card) events."""

    SUCCESS = "SUCCESS"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class SpinOutcome(str, Enum):
    """Outcomes for SPIN events."""

    CARD_WIN = "CARD_WIN"
    CLAIM_WIN = "CLAIM_WIN"
    LOSS = "LOSS"
    NO_SPINS = "NO_SPINS"
    ERROR = "ERROR"


class MegaspinOutcome(str, Enum):
    """Outcomes for MEGASPIN events."""

    SUCCESS = "SUCCESS"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


class MinesweeperOutcome(str, Enum):
    """Outcomes for MINESWEEPER events."""

    CREATED = "CREATED"
    WON = "WON"
    LOST = "LOST"
    ERROR = "ERROR"


class RtbOutcome(str, Enum):
    """Outcomes for RTB (Ride the Bus) events."""

    STARTED = "STARTED"
    WON = "WON"
    LOST = "LOST"
    CASHED_OUT = "CASHED_OUT"
    ERROR = "ERROR"


# --- Validation mapping ---

VALID_OUTCOMES: Dict[EventType, Type[Enum]] = {
    EventType.ROLL: RollOutcome,
    EventType.REROLL: RerollOutcome,
    EventType.CLAIM: ClaimOutcome,
    EventType.TRADE: TradeOutcome,
    EventType.LOCK: LockOutcome,
    EventType.ROLL_LOCK: RollLockOutcome,
    EventType.BURN: BurnOutcome,
    EventType.REFRESH: RefreshOutcome,
    EventType.RECYCLE: RecycleOutcome,
    EventType.CREATE: CreateOutcome,
    EventType.SPIN: SpinOutcome,
    EventType.MEGASPIN: MegaspinOutcome,
    EventType.MINESWEEPER: MinesweeperOutcome,
    EventType.RTB: RtbOutcome,
}


def validate_outcome(event_type: EventType, outcome: Enum) -> None:
    """
    Validate that an outcome is valid for the given event type.

    Args:
        event_type: The event type being logged.
        outcome: The outcome enum value.

    Raises:
        ValueError: If the outcome is not valid for the event type.
    """
    expected_enum = VALID_OUTCOMES.get(event_type)
    if expected_enum is None:
        raise ValueError(f"Unknown event type: {event_type}")

    if not isinstance(outcome, expected_enum):
        valid_values = [e.value for e in expected_enum]
        raise ValueError(
            f"Invalid outcome '{outcome}' for event type '{event_type}'. "
            f"Valid outcomes: {valid_values}"
        )
