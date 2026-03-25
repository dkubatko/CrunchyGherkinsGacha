"""Event manager — event logging with observer pattern.

Implements the observer pattern for telemetry event logging and
notification of subscribers (e.g. achievement processors).
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
from enum import Enum
from typing import Any, Callable, List, Optional

from utils.events import EventType, validate_outcome
from utils.schemas import Event

from repos import event_repo

logger = logging.getLogger(__name__)

# Observer registry with thread safety
_observers: List[Callable[[Event], None]] = []
_observers_lock = threading.Lock()


def subscribe(callback: Callable[[Event], None]) -> None:
    """
    Subscribe to event notifications.

    The callback will be called synchronously after each event is logged.
    If your callback is slow, consider spawning a thread/task inside it.

    Args:
        callback: Function that takes an Event and returns None.
    """
    with _observers_lock:
        if callback not in _observers:
            _observers.append(callback)


def unsubscribe(callback: Callable[[Event], None]) -> None:
    """
    Unsubscribe from event notifications.

    Args:
        callback: The previously subscribed callback to remove.
    """
    with _observers_lock:
        if callback in _observers:
            _observers.remove(callback)
            logger.debug("Event observer unsubscribed: %s", callback.__name__)


def _notify_observers(event: Event) -> None:
    """Notify all subscribed observers of a new event."""
    with _observers_lock:
        observers_copy = list(_observers)

    for observer in observers_copy:
        try:
            observer(event)
        except Exception as e:
            logger.error(
                "Observer %s raised exception for event %s.%s: %s",
                observer.__name__,
                event.event_type,
                event.outcome,
                e,
                exc_info=True,
            )


def log(
    event_type: EventType,
    outcome: Enum,
    user_id: int,
    chat_id: str,
    card_id: Optional[int] = None,
    aspect_id: Optional[int] = None,
    **payload: Any,
) -> Optional[Event]:
    """
    Log a telemetry event to the database and notify observers.

    Args:
        event_type: The type of event (from EventType enum).
        outcome: The outcome of the event (from the corresponding outcome enum).
        user_id: The user who triggered the event.
        chat_id: The chat where the event occurred.
        card_id: Optional card ID associated with the event.
        aspect_id: Optional aspect ID associated with the event.
        **payload: Additional event-specific data (stored as JSON).

    Returns:
        The created Event schema, or None if logging failed.

    Raises:
        ValueError: If the outcome is not valid for the event type.

    Example:
        event_manager.log(
            EventType.SPIN,
            SpinOutcome.CARD_WIN,
            user_id=123,
            chat_id="-100456",
            rarity="epic",
            source_type="character",
            source_id=42,
        )
    """
    # Validate event_type and outcome combination
    validate_outcome(event_type, outcome)

    # JSONB column accepts native Python dicts directly
    payload_data: Optional[dict] = None
    if payload:
        try:
            # Ensure all values are JSON-serializable by round-tripping
            payload_data = json.loads(json.dumps(payload, default=str))
        except (TypeError, ValueError) as e:
            logger.warning("Failed to serialize event payload: %s", e)
            payload_data = {"_serialization_error": str(e)}

    timestamp = datetime.datetime.now(datetime.timezone.utc)

    try:
        event = event_repo.create_event(
            event_type=event_type.value,
            outcome=outcome.value,
            user_id=user_id,
            chat_id=str(chat_id),
            card_id=card_id,
            aspect_id=aspect_id,
            timestamp=timestamp,
            payload=payload_data,
        )

        # Notify observers after commit
        # Preserve original payload kwargs for observers
        if payload:
            event.payload = payload

        _notify_observers(event)

        logger.debug(
            "Event logged: %s.%s user=%s chat=%s card=%s aspect=%s",
            event_type.value,
            outcome.value,
            user_id,
            chat_id,
            card_id,
            aspect_id,
        )

        return event

    except Exception as e:
        logger.error(
            "Failed to log event %s.%s for user %s: %s",
            event_type.value,
            outcome.value,
            user_id,
            e,
            exc_info=True,
        )
        return None
