"""Character service for managing custom characters.

This module provides all character-related business logic including
creating, retrieving, updating, and deleting characters.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from sqlalchemy import func

from utils.models import CharacterModel
from utils.schemas import Character
from utils.session import get_session

logger = logging.getLogger(__name__)

# Import GeminiUtil for slot icon generation
try:
    from utils.gemini import GeminiUtil

    GEMINI_AVAILABLE = True
except ImportError:
    logger.warning("GeminiUtil not available. Slot icon generation will be skipped.")
    GEMINI_AVAILABLE = False


def _generate_slot_icon(image_b64: str) -> Optional[str]:
    """Generate slot machine icon from base64 image. Returns base64 slot icon or None if failed."""
    if not GEMINI_AVAILABLE:
        return None

    try:
        # Get API credentials from environment
        google_api_key = os.getenv("GOOGLE_API_KEY")
        image_gen_model = os.getenv("IMAGE_GEN_MODEL")

        if not google_api_key or not image_gen_model:
            logger.warning(
                "GOOGLE_API_KEY or IMAGE_GEN_MODEL not set, skipping slot icon generation"
            )
            return None

        gemini_util = GeminiUtil(google_api_key, image_gen_model)
        slot_icon_b64 = gemini_util.generate_slot_machine_icon(base_image_b64=image_b64)
        if slot_icon_b64:
            logger.info("Slot machine icon generated successfully")
        else:
            logger.warning("Failed to generate slot machine icon")
        return slot_icon_b64
    except Exception as e:
        logger.error(f"Error generating slot machine icon: {e}")
        return None


def add_character(chat_id: str, name: str, imageb64: str) -> int:
    """Add a new character to the database and generate slot icon."""
    # Generate slot machine icon
    slot_icon_b64 = _generate_slot_icon(imageb64)

    with get_session(commit=True) as session:
        character = CharacterModel(
            chat_id=str(chat_id),
            name=name,
            imageb64=imageb64,
            slot_iconb64=slot_icon_b64,
        )
        session.add(character)
        session.flush()

        if slot_icon_b64:
            logger.info(f"Added character '{name}' with slot icon to chat {chat_id}")
        else:
            logger.info(f"Added character '{name}' to chat {chat_id} (slot icon generation failed)")

        return character.id


def get_character_by_name(chat_id: str, name: str) -> Optional[Character]:
    """Fetch the most recently added character for a chat by case-insensitive name."""
    with get_session() as session:
        character = (
            session.query(CharacterModel)
            .filter(
                CharacterModel.chat_id == str(chat_id),
                func.lower(CharacterModel.name) == func.lower(name),
            )
            .order_by(CharacterModel.id.desc())
            .first()
        )
        return Character.from_orm(character) if character else None


def update_character_image(character_id: int, imageb64: str) -> bool:
    """Update a character's image and regenerate the slot icon when possible."""
    slot_icon_b64 = _generate_slot_icon(imageb64)

    with get_session(commit=True) as session:
        character = session.query(CharacterModel).filter(CharacterModel.id == character_id).first()
        if not character:
            return False

        character.imageb64 = imageb64
        if slot_icon_b64:
            character.slot_iconb64 = slot_icon_b64
            logger.info("Updated character %s image and regenerated slot icon", character_id)
        else:
            logger.info(
                "Updated character %s image (slot icon unchanged due to generation failure)",
                character_id,
            )
        return True


def delete_characters_by_name(name: str) -> int:
    """Delete all characters with the given name (case-insensitive). Returns count of deleted characters."""
    with get_session(commit=True) as session:
        deleted = (
            session.query(CharacterModel)
            .filter(func.lower(CharacterModel.name) == func.lower(name))
            .delete(synchronize_session=False)
        )
        return deleted


def get_characters_by_chat(chat_id: str) -> List[Character]:
    """Get all characters for a specific chat."""
    with get_session() as session:
        characters = (
            session.query(CharacterModel).filter(CharacterModel.chat_id == str(chat_id)).all()
        )
        return [Character.from_orm(c) for c in characters]


def get_character_by_id(character_id: int) -> Optional[Character]:
    """Get a character by its ID."""
    with get_session() as session:
        character = session.query(CharacterModel).filter(CharacterModel.id == character_id).first()
        return Character.from_orm(character) if character else None
