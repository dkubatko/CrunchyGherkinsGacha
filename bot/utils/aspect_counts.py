"""Aspect count event listener.

Subscribes to the event manager and increments aspect-definition usage
counts whenever a new aspect is created (rolled, rerolled, recycled,
forged, or won from casino).  Card-only events are ignored.

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

# Events that represent successful aspect creation (NOT card creation)
ASPECT_CREATION_EVENTS = {
    ("ROLL", "SUCCESS"),
    ("REROLL", "SUCCESS"),
    ("RECYCLE", "SUCCESS"),
    ("CREATE", "SUCCESS"),
    ("SPIN", "ASPECT_WIN"),
    ("MEGASPIN", "ASPECT_WIN"),
    ("MINESWEEPER", "WON"),
}


def _on_aspect_creation(event) -> None:
    """Increment aspect-definition usage count when a new aspect is created.

    Extracts the aspect name from ``payload.aspect_name``.  Falls back to
    looking up the aspect by ``event.aspect_id`` when the payload lacks an
    explicit name.  Events without an identifiable aspect (e.g. card-only
    rolls) are silently skipped.
    """
    if (event.event_type, event.outcome) not in ASPECT_CREATION_EVENTS:
        return

    payload = event.payload or {}

    name = payload.get("aspect_name")
    definition_id = payload.get("aspect_definition_id")

    # Fallback: look up the owned aspect by event.aspect_id when name is missing
    if not name and getattr(event, "aspect_id", None):
        try:
            from repos import aspect_repo

            aspect = aspect_repo.get_aspect_by_id(event.aspect_id)
            if aspect:
                name = aspect.display_name
                if not definition_id and aspect.aspect_definition_id:
                    definition_id = aspect.aspect_definition_id
        except Exception as exc:
            LOGGER.warning(
                "Failed to look up aspect %s for count tracking: %s",
                event.aspect_id,
                exc,
            )

    if not name:
        return

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
    """Subscribe the aspect-count listener to the event manager.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _aspect_count_initialized

    from managers import event_manager

    with _aspect_count_init_lock:
        if _aspect_count_initialized:
            LOGGER.debug("Aspect count listener already initialized")
            return

        event_manager.subscribe(_on_aspect_creation)
        _aspect_count_initialized = True
        LOGGER.info("Aspect count listener initialized")
