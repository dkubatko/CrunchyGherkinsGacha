"""User service for managing users and chat memberships.

This module provides all user-related business logic including
user CRUD operations and chat membership management.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from utils.models import CardModel, CharacterModel, ChatModel, UserModel
from utils.schemas import User
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


def get_username_for_user_id(user_id: int) -> Optional[str]:
    """Return the username associated with a user_id, falling back to card ownership."""
    with get_session() as session:
        user = session.query(UserModel).filter(UserModel.user_id == user_id).first()
        if user and user.username:
            return user.username

        # Fallback: check card ownership
        card = (
            session.query(CardModel.owner)
            .filter(CardModel.user_id == user_id, CardModel.owner.isnot(None))
            .order_by(CardModel.created_at.desc())
            .first()
        )
        if card and card[0]:
            return card[0]
        return None


def get_user_id_by_username(username: str) -> Optional[int]:
    """Resolve a username to a user_id if available."""
    with get_session() as session:
        user = (
            session.query(UserModel)
            .filter(func.lower(UserModel.username) == func.lower(username))
            .first()
        )
        if user:
            return user.user_id

        # Fallback: check card ownership
        card = (
            session.query(CardModel.user_id)
            .filter(
                func.lower(CardModel.owner) == func.lower(username),
                CardModel.user_id.isnot(None),
            )
            .order_by(CardModel.created_at.desc())
            .first()
        )
        if card and card[0] is not None:
            return int(card[0])
        return None


def get_most_frequent_chat_id_for_user(user_id: int) -> Optional[str]:
    """
    Get the most frequently used chat_id among a user's cards.

    Args:
        user_id: The user's ID

    Returns:
        The most frequently used chat_id, or None if user has no cards
    """
    with get_session() as session:
        result = (
            session.query(CardModel.chat_id, func.count(CardModel.id).label("count"))
            .filter(CardModel.user_id == user_id, CardModel.chat_id.isnot(None))
            .group_by(CardModel.chat_id)
            .order_by(func.count(CardModel.id).desc())
            .first()
        )
        if result and result[0]:
            return str(result[0])
        return None


def upsert_user(
    user_id: int,
    username: str,
    display_name: Optional[str] = None,
    profile_imageb64: Optional[str] = None,
) -> None:
    """Insert or update a user record."""
    with get_session(commit=True) as session:
        user = session.query(UserModel).filter(UserModel.user_id == user_id).first()
        if user:
            user.username = username
            if display_name is not None:
                user.display_name = display_name
            if profile_imageb64 is not None:
                user.profile_imageb64 = profile_imageb64
        else:
            user = UserModel(
                user_id=user_id,
                username=username,
                display_name=display_name,
                profile_imageb64=profile_imageb64,
            )
            session.add(user)


def update_user_profile(user_id: int, display_name: str, profile_imageb64: str) -> bool:
    """Update the display name and profile image for a user, and generate slot icon."""
    # Generate slot machine icon
    slot_icon_b64 = _generate_slot_icon(profile_imageb64)

    with get_session(commit=True) as session:
        user = session.query(UserModel).filter(UserModel.user_id == user_id).first()
        if not user:
            return False

        user.display_name = display_name
        user.profile_imageb64 = profile_imageb64
        if slot_icon_b64:
            user.slot_iconb64 = slot_icon_b64
            logger.info(f"Updated user profile and slot icon for user {user_id}")
        else:
            logger.info(f"Updated user profile for user {user_id} (slot icon generation failed)")

        return True


def get_user(user_id: int) -> Optional[User]:
    """Fetch a user record by ID."""
    with get_session() as session:
        user_orm = session.query(UserModel).filter(UserModel.user_id == user_id).first()
        return User.from_orm(user_orm) if user_orm else None


def user_exists(user_id: int) -> bool:
    """Check whether a user exists in the users table."""
    with get_session() as session:
        return session.query(UserModel).filter(UserModel.user_id == user_id).first() is not None


def get_all_chat_users_with_profile(chat_id: str) -> List[User]:
    """Return all users enrolled in the chat with stored profile images and display names."""
    with get_session() as session:
        users = (
            session.query(UserModel)
            .join(ChatModel, ChatModel.user_id == UserModel.user_id)
            .filter(
                ChatModel.chat_id == str(chat_id),
                UserModel.profile_imageb64.isnot(None),
                func.trim(UserModel.profile_imageb64) != "",
                UserModel.display_name.isnot(None),
                func.trim(UserModel.display_name) != "",
            )
            .all()
        )
        return [User.from_orm(u) for u in users]


def get_random_chat_user_with_profile(chat_id: str) -> Optional[User]:
    """Return a random user enrolled in the chat with a stored profile image."""
    with get_session() as session:
        user = (
            session.query(UserModel)
            .join(ChatModel, ChatModel.user_id == UserModel.user_id)
            .filter(
                ChatModel.chat_id == str(chat_id),
                UserModel.profile_imageb64.isnot(None),
                func.trim(UserModel.profile_imageb64) != "",
                UserModel.display_name.isnot(None),
                func.trim(UserModel.display_name) != "",
            )
            .order_by(func.random())
            .first()
        )
        return User.from_orm(user) if user else None


def add_user_to_chat(chat_id: str, user_id: int) -> bool:
    """Add a user to a chat; returns True if inserted."""
    with get_session(commit=True) as session:
        existing = (
            session.query(ChatModel)
            .filter(
                ChatModel.chat_id == str(chat_id),
                ChatModel.user_id == user_id,
            )
            .first()
        )
        if existing:
            return False
        chat = ChatModel(chat_id=str(chat_id), user_id=user_id)
        session.add(chat)
        return True


def remove_user_from_chat(chat_id: str, user_id: int) -> bool:
    """Remove a user from a chat; returns True if a row was deleted."""
    with get_session(commit=True) as session:
        deleted = (
            session.query(ChatModel)
            .filter(
                ChatModel.chat_id == str(chat_id),
                ChatModel.user_id == user_id,
            )
            .delete()
        )
        return deleted > 0


def is_user_in_chat(chat_id: str, user_id: int) -> bool:
    """Check whether a user is enrolled in a chat."""
    with get_session() as session:
        return (
            session.query(ChatModel)
            .filter(
                ChatModel.chat_id == str(chat_id),
                ChatModel.user_id == user_id,
            )
            .first()
            is not None
        )


def get_all_chat_users(chat_id: str) -> List[int]:
    """Get all user IDs enrolled in a specific chat."""
    with get_session() as session:
        chats = session.query(ChatModel.user_id).filter(ChatModel.chat_id == str(chat_id)).all()
        return [c[0] for c in chats]


def get_chat_users_and_characters(chat_id: str) -> List[Dict[str, Any]]:
    """Get all users and characters for a specific chat with id, display_name/name, slot_iconb64, and type."""
    with get_session() as session:
        # Get users
        user_results = (
            session.query(
                UserModel.user_id.label("id"),
                UserModel.display_name,
                UserModel.slot_iconb64,
            )
            .join(ChatModel, ChatModel.user_id == UserModel.user_id)
            .filter(ChatModel.chat_id == str(chat_id))
            .all()
        )

        # Get characters
        char_results = (
            session.query(
                CharacterModel.id,
                CharacterModel.name.label("display_name"),
                CharacterModel.slot_iconb64,
            )
            .filter(CharacterModel.chat_id == str(chat_id))
            .all()
        )

    all_items = []
    for row in user_results:
        all_items.append(
            {
                "id": row.id,
                "display_name": row.display_name,
                "slot_iconb64": row.slot_iconb64,
                "type": "user",
            }
        )
    for row in char_results:
        all_items.append(
            {
                "id": row.id,
                "display_name": row.display_name,
                "slot_iconb64": row.slot_iconb64,
                "type": "character",
            }
        )

    return all_items
