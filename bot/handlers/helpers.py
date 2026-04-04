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

    Returns a human-readable string like:
    - "less than a minute"
    - "23 minutes"
    - "5 hours 12 minutes"
    Returns None if the user can roll now.
    """
    last_roll_time = roll_repo.get_last_roll_time(user_id, chat_id)
    if last_roll_time is None:
        return None

    now = datetime.datetime.now(timezone.utc)
    next_roll_time = last_roll_time + datetime.timedelta(hours=24)
    total_seconds = (next_roll_time - now).total_seconds()

    if total_seconds <= 0:
        return None

    if total_seconds < 60:
        return "less than a minute"

    total_minutes = int(total_seconds // 60)
    if total_minutes < 60:
        return f"{total_minutes} minute{'s' if total_minutes != 1 else ''}"

    hours = total_minutes // 60
    minutes = total_minutes % 60
    parts = [f"{hours} hour{'s' if hours != 1 else ''}"]
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return " ".join(parts)


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
    """Build the burning animation text for card/aspect recycling/burning."""
    header = f"Burning {item_label}..."
    if revealed <= 0:
        return header

    emoji = "🔮" if item_label == "aspects" else "🃏"
    lines = []
    for idx in range(revealed):
        line = f"🔥{emoji} {card_titles[idx]}🔥"
        if strike_all or idx < revealed - 1:
            line = f"<s>{line}</s>"
        lines.append(line)

    return f"{header}\n\n" + "\n".join(lines)


def format_aspect_list(card, total_slots: int = 5) -> str:
    """Format equipped aspects block: 'Equipped aspects (x/N):' + bullet list.

    Returns empty string when the card has no aspects equipped.
    """
    names: list[str] = []
    if card and card.equipped_aspects:
        for ca in card.equipped_aspects:
            if ca.aspect and ca.aspect.display_name:
                names.append(f"🔮 {ca.aspect.display_name}")
            elif ca.aspect and ca.aspect.name:
                names.append(f"🔮 {ca.aspect.name}")
    if not names:
        return ""
    count = card.aspect_count if card else len(names)
    return f"Equipped aspects ({count}/{total_slots}):\n\n" + "\n".join(names)
