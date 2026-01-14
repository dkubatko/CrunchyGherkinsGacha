"""Modifier count service for database operations on modifier frequency tracking.

This module provides database operations for modifier occurrence counts per chat per season.
The event listener that updates these counts lives in utils.modifiers.

Usage:
    from utils.services import modifier_count_service

    # Increment count when a card is created
    modifier_count_service.increment_count(chat_id="-100123", season_id=1, modifier="Cosmic")

    # Get all modifier counts for a chat/season
    counts = modifier_count_service.get_counts(chat_id="-100123", season_id=1)
    # Returns: {"Cosmic": 5, "Ancient": 3, ...}
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from settings.constants import CURRENT_SEASON
from utils.models import ModifierCountModel
from utils.session import get_session

logger = logging.getLogger(__name__)


def increment_count(
    chat_id: str,
    modifier: str,
    season_id: Optional[int] = None,
    increment: int = 1,
) -> None:
    """
    Increment the count for a modifier in a specific chat and season.

    Uses upsert semantics: if the row exists, increment the count;
    otherwise, insert a new row with the initial count.

    Args:
        chat_id: The chat ID where the card was created.
        modifier: The modifier that was used.
        season_id: The season ID. Defaults to CURRENT_SEASON.
        increment: The amount to increment by. Defaults to 1.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    try:
        with get_session(commit=True) as session:
            # Try to find existing record
            existing = (
                session.query(ModifierCountModel)
                .filter(
                    ModifierCountModel.chat_id == str(chat_id),
                    ModifierCountModel.season_id == season_id,
                    ModifierCountModel.modifier == modifier,
                )
                .first()
            )

            if existing:
                # Update existing count
                existing.count += increment
            else:
                # Insert new record
                new_record = ModifierCountModel(
                    chat_id=str(chat_id),
                    season_id=season_id,
                    modifier=modifier,
                    count=increment,
                )
                session.add(new_record)

        logger.debug(
            "Incremented modifier count: chat=%s season=%s modifier=%s increment=%d",
            chat_id,
            season_id,
            modifier,
            increment,
        )
    except Exception as e:
        logger.error(
            "Failed to increment modifier count for chat=%s modifier=%s: %s",
            chat_id,
            modifier,
            e,
            exc_info=True,
        )


def get_counts(
    chat_id: str,
    season_id: Optional[int] = None,
) -> Dict[str, int]:
    """
    Get all modifier counts for a specific chat and season.

    Args:
        chat_id: The chat ID to get counts for.
        season_id: The season ID. Defaults to CURRENT_SEASON.

    Returns:
        A dictionary mapping modifier names to their occurrence counts.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    try:
        with get_session() as session:
            results = (
                session.query(ModifierCountModel)
                .filter(
                    ModifierCountModel.chat_id == str(chat_id),
                    ModifierCountModel.season_id == season_id,
                )
                .all()
            )

            return {row.modifier: row.count for row in results}
    except Exception as e:
        logger.error(
            "Failed to get modifier counts for chat=%s season=%s: %s",
            chat_id,
            season_id,
            e,
            exc_info=True,
        )
        return {}


def get_count(
    chat_id: str,
    modifier: str,
    season_id: Optional[int] = None,
) -> int:
    """
    Get the count for a specific modifier in a chat and season.

    Args:
        chat_id: The chat ID to get the count for.
        modifier: The modifier to get the count for.
        season_id: The season ID. Defaults to CURRENT_SEASON.

    Returns:
        The occurrence count for the modifier, or 0 if not found.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    try:
        with get_session() as session:
            result = (
                session.query(ModifierCountModel)
                .filter(
                    ModifierCountModel.chat_id == str(chat_id),
                    ModifierCountModel.season_id == season_id,
                    ModifierCountModel.modifier == modifier,
                )
                .first()
            )

            return result.count if result else 0
    except Exception as e:
        logger.error(
            "Failed to get modifier count for chat=%s modifier=%s: %s",
            chat_id,
            modifier,
            e,
            exc_info=True,
        )
        return 0


def reset_counts(
    chat_id: str,
    season_id: Optional[int] = None,
) -> None:
    """
    Reset all modifier counts for a specific chat and season.

    This is primarily used for testing or administrative purposes.

    Args:
        chat_id: The chat ID to reset counts for.
        season_id: The season ID. Defaults to CURRENT_SEASON.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    try:
        with get_session(commit=True) as session:
            session.query(ModifierCountModel).filter(
                ModifierCountModel.chat_id == str(chat_id),
                ModifierCountModel.season_id == season_id,
            ).delete()

        logger.info(
            "Reset modifier counts for chat=%s season=%s",
            chat_id,
            season_id,
        )
    except Exception as e:
        logger.error(
            "Failed to reset modifier counts for chat=%s season=%s: %s",
            chat_id,
            season_id,
            e,
            exc_info=True,
        )
