"""Event service for telemetry logging with observer pattern.

This module provides event logging functionality for tracking user actions
and game events. It supports an observer pattern for achievement processing
and other reactive systems.

Usage:
    from utils.services import event_service
    from utils.events import EventType, RollOutcome

    # Log an event
    event_service.log(
        EventType.ROLL,
        RollOutcome.SUCCESS,
        user_id=123,
        chat_id="-100123456",
        card_id=789,
        rarity="legendary",
        source_type="user",
    )

    # Subscribe to events (for achievement processing)
    def on_event(event):
        if event.event_type == "ROLL" and event.outcome == "SUCCESS":
            check_roll_achievements(event.user_id, event.payload)

    event_service.subscribe(on_event)
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from utils.events import EventType, validate_outcome
from utils.models import EventModel
from utils.schemas import Event
from utils.session import get_session

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
        **payload: Additional event-specific data (stored as JSON).

    Returns:
        The created Event schema, or None if logging failed.

    Raises:
        ValueError: If the outcome is not valid for the event type.

    Example:
        event_service.log(
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

    # Serialize payload to JSON
    payload_json: Optional[str] = None
    if payload:
        try:
            payload_json = json.dumps(payload, default=str)
        except (TypeError, ValueError) as e:
            logger.warning("Failed to serialize event payload: %s", e)
            payload_json = json.dumps({"_serialization_error": str(e)})

    timestamp = datetime.datetime.now(datetime.timezone.utc)

    try:
        with get_session(commit=True) as session:
            event_model = EventModel(
                event_type=event_type.value,
                outcome=outcome.value,
                user_id=user_id,
                chat_id=str(chat_id),
                card_id=card_id,
                timestamp=timestamp,
                payload=payload_json,
            )
            session.add(event_model)
            session.flush()  # Get the ID

            # Convert to schema for return and observer notification
            event = Event(
                id=event_model.id,
                event_type=event_model.event_type,
                outcome=event_model.outcome,
                user_id=event_model.user_id,
                chat_id=event_model.chat_id,
                card_id=event_model.card_id,
                timestamp=timestamp,
                payload=payload if payload else None,
            )

        # Notify observers after commit
        _notify_observers(event)

        logger.debug(
            "Event logged: %s.%s user=%s chat=%s card=%s",
            event_type.value,
            outcome.value,
            user_id,
            chat_id,
            card_id,
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


def get_events_by_user(
    user_id: int,
    event_types: Optional[List[EventType]] = None,
    limit: int = 100,
) -> List[Event]:
    """
    Get events for a specific user.

    Args:
        user_id: The user ID to filter by.
        event_types: Optional list of event types to filter by.
        limit: Maximum number of events to return.

    Returns:
        List of Event schemas, ordered by timestamp descending.
    """
    with get_session() as session:
        query = session.query(EventModel).filter(EventModel.user_id == user_id)

        if event_types:
            type_values = [et.value for et in event_types]
            query = query.filter(EventModel.event_type.in_(type_values))

        query = query.order_by(EventModel.timestamp.desc()).limit(limit)

        return [Event.from_orm(e) for e in query.all()]


def get_events_by_card(card_id: int, limit: int = 100) -> List[Event]:
    """
    Get events associated with a specific card.

    Args:
        card_id: The card ID to filter by.
        limit: Maximum number of events to return.

    Returns:
        List of Event schemas, ordered by timestamp descending.
    """
    with get_session() as session:
        query = (
            session.query(EventModel)
            .filter(EventModel.card_id == card_id)
            .order_by(EventModel.timestamp.desc())
            .limit(limit)
        )

        return [Event.from_orm(e) for e in query.all()]


def get_events_by_chat(
    chat_id: str,
    event_types: Optional[List[EventType]] = None,
    limit: int = 100,
) -> List[Event]:
    """
    Get events for a specific chat.

    Args:
        chat_id: The chat ID to filter by.
        event_types: Optional list of event types to filter by.
        limit: Maximum number of events to return.

    Returns:
        List of Event schemas, ordered by timestamp descending.
    """
    with get_session() as session:
        query = session.query(EventModel).filter(EventModel.chat_id == str(chat_id))

        if event_types:
            type_values = [et.value for et in event_types]
            query = query.filter(EventModel.event_type.in_(type_values))

        query = query.order_by(EventModel.timestamp.desc()).limit(limit)

        return [Event.from_orm(e) for e in query.all()]


def count_events(
    user_id: Optional[int] = None,
    chat_id: Optional[str] = None,
    event_type: Optional[EventType] = None,
    outcome: Optional[Enum] = None,
) -> int:
    """
    Count events matching the given filters.

    Args:
        user_id: Optional user ID filter.
        chat_id: Optional chat ID filter.
        event_type: Optional event type filter.
        outcome: Optional outcome filter.

    Returns:
        Count of matching events.
    """
    with get_session() as session:
        query = session.query(EventModel)

        if user_id is not None:
            query = query.filter(EventModel.user_id == user_id)
        if chat_id is not None:
            query = query.filter(EventModel.chat_id == str(chat_id))
        if event_type is not None:
            query = query.filter(EventModel.event_type == event_type.value)
        if outcome is not None:
            query = query.filter(EventModel.outcome == outcome.value)

        return query.count()
