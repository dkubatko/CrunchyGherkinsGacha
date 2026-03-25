"""Aspect count repository for tracking aspect definition usage frequency.

This module provides database operations for aspect-definition occurrence
counts per chat per season via the ``aspect_counts`` table
(``AspectCountModel``).

The event listener that updates these counts lives in
``utils.aspect_counts``.

Usage:
    from repos import aspect_count_repo

    # Increment count when an aspect is rolled
    aspect_count_repo.increment_count(
        chat_id="-100123", season_id=1, name="Rainy", definition_id=42,
    )

    # Get all aspect-definition counts for a chat/season
    counts = aspect_count_repo.get_counts(chat_id="-100123", season_id=1)
    # Returns: {"Rainy": 5, "Ancient": 3, ...}
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from sqlalchemy.orm import Session

from settings.constants import CURRENT_SEASON
from utils.models import AspectCountModel
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session(commit=True)
def increment_count(
    chat_id: str,
    name: str,
    season_id: Optional[int] = None,
    definition_id: Optional[int] = None,
    increment: int = 1,
    *,
    session: Session,
) -> None:
    """Increment the count for an aspect definition in a chat/season.

    Uses upsert semantics: if the row exists, increment; otherwise insert.

    Args:
        chat_id: The chat ID where the aspect was rolled.
        name: The aspect definition name.
        season_id: The season ID.  Defaults to ``CURRENT_SEASON``.
        definition_id: The aspect definition's DB ID (optional).
        increment: The amount to increment by.  Defaults to 1.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    try:
        existing = (
            session.query(AspectCountModel)
            .filter(
                AspectCountModel.chat_id == str(chat_id),
                AspectCountModel.season_id == season_id,
                AspectCountModel.name == name,
            )
            .first()
        )

        if existing:
            existing.count += increment
            if definition_id is not None and existing.definition_id is None:
                existing.definition_id = definition_id
        else:
            new_record = AspectCountModel(
                chat_id=str(chat_id),
                season_id=season_id,
                name=name,
                definition_id=definition_id,
                count=increment,
            )
            session.add(new_record)

        logger.debug(
            "Incremented aspect count: chat=%s season=%s name=%s def_id=%s increment=%d",
            chat_id,
            season_id,
            name,
            definition_id,
            increment,
        )
    except Exception as e:
        logger.error(
            "Failed to increment aspect count for chat=%s name=%s: %s",
            chat_id,
            name,
            e,
            exc_info=True,
        )


@with_session
def get_counts(
    chat_id: str,
    season_id: Optional[int] = None,
    *,
    session: Session,
) -> Dict[str, int]:
    """Get all aspect-definition counts for a specific chat and season.

    Returns:
        A dictionary mapping aspect-definition names to occurrence counts.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    try:
        results = (
            session.query(AspectCountModel)
            .filter(
                AspectCountModel.chat_id == str(chat_id),
                AspectCountModel.season_id == season_id,
            )
            .all()
        )

        return {row.name: row.count for row in results}
    except Exception as e:
        logger.error(
            "Failed to get aspect counts for chat=%s season=%s: %s",
            chat_id,
            season_id,
            e,
            exc_info=True,
        )
        return {}


@with_session
def get_count(
    chat_id: str,
    name: str,
    season_id: Optional[int] = None,
    *,
    session: Session,
) -> int:
    """Get the count for a specific aspect definition in a chat/season.

    Returns:
        The occurrence count, or 0 if not found.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    try:
        result = (
            session.query(AspectCountModel)
            .filter(
                AspectCountModel.chat_id == str(chat_id),
                AspectCountModel.season_id == season_id,
                AspectCountModel.name == name,
            )
            .first()
        )

        return result.count if result else 0
    except Exception as e:
        logger.error(
            "Failed to get aspect count for chat=%s name=%s: %s",
            chat_id,
            name,
            e,
            exc_info=True,
        )
        return 0


@with_session(commit=True)
def reset_counts(
    chat_id: str,
    season_id: Optional[int] = None,
    *,
    session: Session,
) -> None:
    """Reset all aspect-definition counts for a chat/season.

    Primarily used for testing or administrative purposes.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    try:
        session.query(AspectCountModel).filter(
            AspectCountModel.chat_id == str(chat_id),
            AspectCountModel.season_id == season_id,
        ).delete()

        logger.info(
            "Reset aspect counts for chat=%s season=%s",
            chat_id,
            season_id,
        )
    except Exception as e:
        logger.error(
            "Failed to reset aspect counts for chat=%s season=%s: %s",
            chat_id,
            season_id,
            e,
            exc_info=True,
        )
