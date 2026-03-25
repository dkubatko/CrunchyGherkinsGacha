"""Character repository for managing custom characters.

This module provides all character-related data access operations including
creating, retrieving, updating, and deleting characters.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from utils.models import CharacterModel
from utils.schemas import Character
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session(commit=True)
def add_character(chat_id: str, name: str, imageb64: str, slot_icon_b64: Optional[str] = None, *, session: Session) -> int:
    """Add a new character to the database."""
    import base64

    character = CharacterModel(
        chat_id=str(chat_id),
        name=name,
        image=base64.b64decode(imageb64),
        slot_icon=base64.b64decode(slot_icon_b64) if slot_icon_b64 else None,
    )
    session.add(character)
    session.flush()

    if slot_icon_b64:
        logger.info(f"Added character '{name}' with slot icon to chat {chat_id}")
    else:
        logger.info(f"Added character '{name}' to chat {chat_id} (slot icon generation failed)")

    return character.id


@with_session
def get_character_by_name(chat_id: str, name: str, *, session: Session) -> Optional[Character]:
    """Fetch the most recently added character for a chat by case-insensitive name."""
    result = (
        session.query(CharacterModel)
        .filter(
            CharacterModel.chat_id == str(chat_id),
            func.lower(CharacterModel.name) == func.lower(name),
        )
        .order_by(CharacterModel.id.desc())
        .first()
    )
    return Character.from_orm(result) if result else None


@with_session(commit=True)
def update_character_image(character_id: int, imageb64: str, slot_icon_b64: Optional[str] = None, *, session: Session) -> bool:
    """Update a character's image and optionally its slot icon."""
    import base64

    character = session.query(CharacterModel).filter(CharacterModel.id == character_id).first()
    if not character:
        return False

    character.image = base64.b64decode(imageb64)
    if slot_icon_b64:
        character.slot_icon = base64.b64decode(slot_icon_b64)
        logger.info("Updated character %s image and regenerated slot icon", character_id)
    else:
        logger.info(
            "Updated character %s image (slot icon unchanged due to generation failure)",
            character_id,
        )
    return True


@with_session(commit=True)
def delete_characters_by_name(name: str, *, session: Session) -> int:
    """Delete all characters with the given name (case-insensitive). Returns count of deleted characters."""
    deleted = (
        session.query(CharacterModel)
        .filter(func.lower(CharacterModel.name) == func.lower(name))
        .delete(synchronize_session=False)
    )
    return deleted


@with_session
def get_characters_by_chat(chat_id: str, *, session: Session) -> List[Character]:
    """Get all characters for a specific chat."""
    results = session.query(CharacterModel).filter(CharacterModel.chat_id == str(chat_id)).all()
    return [Character.from_orm(r) for r in results]


@with_session
def get_character_by_id(character_id: int, *, session: Session) -> Optional[Character]:
    """Get a character by its ID."""
    result = session.query(CharacterModel).filter(CharacterModel.id == character_id).first()
    return Character.from_orm(result) if result else None
