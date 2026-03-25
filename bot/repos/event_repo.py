"""Event repository for database access to telemetry events.

This module provides data access functions for querying event records.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import List, Optional

from utils.events import EventType
from utils.models import EventModel
from utils.schemas import Event
from sqlalchemy.orm import Session
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session(commit=True)
def create_event(
    event_type: str,
    outcome: str,
    user_id: int,
    chat_id: str,
    timestamp,
    card_id: Optional[int] = None,
    aspect_id: Optional[int] = None,
    payload: Optional[dict] = None,
    *,
    session: Session,
) -> Event:
    """Insert a new event record and return it."""
    event_model = EventModel(
        event_type=event_type,
        outcome=outcome,
        user_id=user_id,
        chat_id=str(chat_id),
        card_id=card_id,
        aspect_id=aspect_id,
        timestamp=timestamp,
        payload=payload,
    )
    session.add(event_model)
    session.flush()

    return Event.from_orm(event_model)


@with_session
def get_events_by_user(
    user_id: int,
    event_types: Optional[List[EventType]] = None,
    outcomes: Optional[List[str]] = None,
    limit: int = 100,
    *,
    session: Session,
) -> List[Event]:
    """
    Get events for a specific user.

    Args:
        user_id: The user ID to filter by.
        event_types: Optional list of event types to filter by.
        outcomes: Optional list of outcome strings to filter by.
        limit: Maximum number of events to return.

    Returns:
        List of Event instances, ordered by timestamp descending.
    """
    query = session.query(EventModel).filter(EventModel.user_id == user_id)

    if event_types:
        type_values = [et.value for et in event_types]
        query = query.filter(EventModel.event_type.in_(type_values))

    if outcomes:
        query = query.filter(EventModel.outcome.in_(outcomes))

    query = query.order_by(EventModel.timestamp.desc()).limit(limit)

    return [Event.from_orm(r) for r in query.all()]


@with_session
def get_events_by_card(card_id: int, limit: int = 100, *, session: Session) -> List[Event]:
    """
    Get events associated with a specific card.

    Args:
        card_id: The card ID to filter by.
        limit: Maximum number of events to return.

    Returns:
        List of Event instances, ordered by timestamp descending.
    """
    query = (
        session.query(EventModel)
        .filter(EventModel.card_id == card_id)
        .order_by(EventModel.timestamp.desc())
        .limit(limit)
    )

    return [Event.from_orm(r) for r in query.all()]


@with_session
def get_events_by_chat(
    chat_id: str,
    event_types: Optional[List[EventType]] = None,
    limit: int = 100,
    *,
    session: Session,
) -> List[Event]:
    """
    Get events for a specific chat.

    Args:
        chat_id: The chat ID to filter by.
        event_types: Optional list of event types to filter by.
        limit: Maximum number of events to return.

    Returns:
        List of Event instances, ordered by timestamp descending.
    """
    query = session.query(EventModel).filter(EventModel.chat_id == str(chat_id))

    if event_types:
        type_values = [et.value for et in event_types]
        query = query.filter(EventModel.event_type.in_(type_values))

    query = query.order_by(EventModel.timestamp.desc()).limit(limit)

    return [Event.from_orm(r) for r in query.all()]


@with_session
def count_events(
    user_id: Optional[int] = None,
    chat_id: Optional[str] = None,
    event_type: Optional[EventType] = None,
    outcome: Optional[Enum] = None,
    *,
    session: Session,
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
