"""
Shared helper functions for bot handlers.

This module contains utility functions used across different handler modules.
"""

import asyncio
import datetime
import logging
from datetime import timezone

from repos import card_repo
from repos import roll_repo
from repos import aspect_repo

logger = logging.getLogger(__name__)


def log_card_generation(generated_card, context="card generation"):
    """Log details about a generated card including its source."""
    logger.info(
        f"Generating card for {context}: {generated_card.source_type}:{generated_card.source_id} "
        f"-> ({generated_card.rarity}) {generated_card.modifier} {generated_card.base_name}"
    )


def get_time_until_next_roll(user_id, chat_id):
    """Calculate time until next roll (24 hours from last roll).
    Uses UTC for consistent timezone handling.
    """
    last_roll_time = roll_repo.get_last_roll_time(user_id, chat_id)
    if last_roll_time is None:
        return 0, 0  # Can roll immediately if never rolled before

    now = datetime.datetime.now(timezone.utc)
    next_roll_time = last_roll_time + datetime.timedelta(hours=24)
    time_diff = next_roll_time - now

    if time_diff.total_seconds() <= 0:
        return 0, 0  # Can roll now

    hours = int(time_diff.total_seconds() // 3600)
    minutes = int((time_diff.total_seconds() % 3600) // 60)

    return hours, minutes


async def save_card_file_id_from_message(message, card_id: int) -> None:
    """
    Extract and save the Telegram file_id from a message containing a card photo.

    Args:
        message: The Telegram message object containing the photo
        card_id: The database ID of the card to update
    """
    if message and message.photo:
        file_id = message.photo[-1].file_id  # Get the largest photo size
        await asyncio.to_thread(card_repo.update_card_file_id, card_id, file_id)
        logger.debug(f"Saved file_id for card {card_id}")


async def save_aspect_file_id_from_message(message, aspect_id: int) -> None:
    """
    Extract and save the Telegram file_id from a message containing an aspect sphere photo.

    Args:
        message: The Telegram message object containing the photo
        aspect_id: The database ID of the owned aspect to update
    """
    if message and message.photo:
        file_id = message.photo[-1].file_id
        await asyncio.to_thread(aspect_repo.update_aspect_file_id, aspect_id, file_id)
        logger.debug(f"Saved file_id for aspect {aspect_id}")


def build_burning_text(
    card_titles: list[str],
    revealed: int,
    strike_all: bool = False,
    item_label: str = "cards",
) -> str:
    """Build the burning animation text for card/aspect recycling/burning.

    Args:
        card_titles: List of HTML-escaped display names for the items being burned.
        revealed: Number of items revealed so far in the animation.
        strike_all: If True, strike through all revealed items.
        item_label: Label for the item type (e.g. "cards", "aspects").
    """
    header = f"Burning {item_label}..."
    if revealed <= 0:
        return header

    lines = []
    for idx in range(revealed):
        line = f"🔥{card_titles[idx]}🔥"
        if strike_all or idx < revealed - 1:
            line = f"<s>{line}</s>"
        lines.append(line)

    return f"{header}\n\n" + "\n".join(lines)
