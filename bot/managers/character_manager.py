"""Character manager — business logic for character operations."""

from __future__ import annotations

import logging
from typing import Optional

from repos import character_repo
from utils.slot_icon import generate_slot_icon

logger = logging.getLogger(__name__)


def add_character(chat_id: str, name: str, imageb64: str) -> int:
    """Add a character with auto-generated slot icon."""
    slot_icon_b64 = generate_slot_icon(imageb64)
    return character_repo.add_character(chat_id, name, imageb64, slot_icon_b64=slot_icon_b64)


def update_character_image(character_id: int, imageb64: str) -> bool:
    """Update a character's image with auto-generated slot icon."""
    slot_icon_b64 = generate_slot_icon(imageb64)
    return character_repo.update_character_image(character_id, imageb64, slot_icon_b64=slot_icon_b64)
