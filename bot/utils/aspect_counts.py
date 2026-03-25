"""Aspect count event listener.

Subscribes to the event service and increments aspect-definition usage
counts whenever a card or aspect is created.  This replaces the legacy
modifier count listener in ``utils.modifiers``.

Start-up entry point: ``init_aspect_count_listener()`` — safe to call
more than once.
"""

from __future__ import annotations

import logging
import threading

from settings.constants import CURRENT_SEASON

LOGGER = logging.getLogger(__name__)

# Track initialisation to prevent double-subscription
_aspect_count_initialized = False
_aspect_count_init_lock = threading.Lock()

# Events that represent successful card/aspect creation
CREATION_EVENTS = {
    ("ROLL", "SUCCESS"),
    ("REROLL", "SUCCESS"),
    ("RECYCLE", "SUCCESS"),
    ("CREATE", "SUCCESS"),
    ("SPIN", "CARD_WIN"),
    ("MEGASPIN", "SUCCESS"),
    ("MINESWEEPER", "WON"),
}


def _on_creation_event(event) -> None:
    """Handle card/aspect creation events by incrementing counts.

    Works for both legacy modifier-based card creations (``payload.modifier``)
    and new aspect-based rolls (``payload.aspect_name``).
    """
    if (event.event_type, event.outcome) not in CREATION_EVENTS:
        return

    if not event.payload:
        return

    # Determine the name to count — prefer new aspect_name, fall back to modifier
    name = event.payload.get("aspect_name") or event.payload.get("modifier")
    if not name:
        return

    definition_id = event.payload.get("aspect_definition_id") or event.payload.get("modifier_id")

    from repos import aspect_count_repo

    aspect_count_repo.increment_count(
        chat_id=event.chat_id,
        name=name,
        definition_id=definition_id,
        season_id=CURRENT_SEASON,
    )

    LOGGER.debug(
        "Incremented aspect count for event %s.%s: chat=%s name=%s def_id=%s",
        event.event_type,
        event.outcome,
        event.chat_id,
        name,
        definition_id,
    )


def init_aspect_count_listener() -> None:
    """Subscribe the aspect-count listener to the event service.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _aspect_count_initialized

    from managers import event_manager

    with _aspect_count_init_lock:
        if _aspect_count_initialized:
            LOGGER.debug("Aspect count listener already initialized")
            return

        event_manager.subscribe(_on_creation_event)
        _aspect_count_initialized = True
        LOGGER.info("Aspect count listener initialized")
