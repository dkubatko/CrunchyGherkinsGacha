"""Modifier event listener and re-exports.

This module provides the modifier count event listener that automatically
increments modifier usage counts when cards are created.  It also
re-exports :class:`Modifier` from the schemas module so that
existing consumers (``gemini.py``, ``generate_single_card.py``, etc.)
continue to work without import changes.

The YAML loading machinery that previously lived here has been removed.
All modifier data now lives in the ``modifiers`` database table and is
accessed via :mod:`utils.services.modifier_service`.
"""

from __future__ import annotations

import logging
import threading

from settings.constants import CURRENT_SEASON

# Re-export Modifier so existing ``from utils.modifiers import Modifier``
# statements keep working without changes.
from utils.schemas import Modifier  # noqa: F401

LOGGER = logging.getLogger(__name__)


# ============================================================================
# Modifier Count Tracking (Event Listener)
# ============================================================================

# Track initialization to prevent double-subscription
_modifier_count_initialized = False
_modifier_count_init_lock = threading.Lock()

# Card creation event types and their success outcomes
CARD_CREATION_EVENTS = {
    ("ROLL", "SUCCESS"),
    ("REROLL", "SUCCESS"),
    ("RECYCLE", "SUCCESS"),
    ("CREATE", "SUCCESS"),
    ("SPIN", "CARD_WIN"),
    ("MEGASPIN", "SUCCESS"),
    ("MINESWEEPER", "WON"),
}


def _on_card_creation_event(event) -> None:
    """
    Handle card creation events by incrementing modifier counts.

    This is called automatically by the event service when events are logged.

    Args:
        event: The event that was logged.
    """
    # Check if this is a card creation event
    if (event.event_type, event.outcome) not in CARD_CREATION_EVENTS:
        return

    # Extract modifier from payload
    if not event.payload:
        LOGGER.debug(
            "Card creation event %s.%s has no payload, skipping modifier count",
            event.event_type,
            event.outcome,
        )
        return

    modifier = event.payload.get("modifier")
    if not modifier:
        LOGGER.debug(
            "Card creation event %s.%s has no modifier in payload, skipping",
            event.event_type,
            event.outcome,
        )
        return

    # Resolve modifier_id from payload if present
    modifier_id = event.payload.get("modifier_id")

    # Increment the modifier count using the service
    from utils.services import modifier_count_service

    modifier_count_service.increment_count(
        chat_id=event.chat_id,
        modifier=modifier,
        modifier_id=modifier_id,
        season_id=CURRENT_SEASON,
    )

    LOGGER.debug(
        "Incremented modifier count for event %s.%s: chat=%s modifier=%s modifier_id=%s",
        event.event_type,
        event.outcome,
        event.chat_id,
        modifier,
        modifier_id,
    )


def init_modifier_count_listener() -> None:
    """
    Initialize the modifier count listener by subscribing to events.

    This should be called once at startup from both bot and API.
    It's safe to call multiple times - subsequent calls are no-ops.
    """
    global _modifier_count_initialized

    from utils.services import event_service

    with _modifier_count_init_lock:
        if _modifier_count_initialized:
            LOGGER.debug("Modifier count listener already initialized")
            return

        event_service.subscribe(_on_card_creation_event)
        _modifier_count_initialized = True
        LOGGER.info("Modifier count listener initialized")
