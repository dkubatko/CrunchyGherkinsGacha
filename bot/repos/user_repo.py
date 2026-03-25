"""User repository for database access to users and chat memberships.

This module provides data access functions for user CRUD operations
and chat membership management.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from utils.models import CardModel, CharacterModel, ChatModel, UserModel
from utils.schemas import User
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session
def get_username_for_user_id(user_id: int, *, session: Session) -> Optional[str]:
    """Return the username associated with a user_id, falling back to card ownership."""
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


@with_session
def get_user_id_by_username(username: str, *, session: Session) -> Optional[int]:
    """Resolve a username to a user_id if available."""
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


@with_session
def get_most_frequent_chat_id_for_user(user_id: int, *, session: Session) -> Optional[str]:
    """
    Get the most frequently used chat_id among a user's cards.

    Args:
        user_id: The user's ID

    Returns:
        The most frequently used chat_id, or None if user has no cards
    """
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


@with_session(commit=True)
def upsert_user(
    user_id: int,
    username: str,
    display_name: Optional[str] = None,
    profile_imageb64: Optional[str] = None,
    *,
    session: Session,
) -> None:
    """Insert or update a user record."""
    import base64

    profile_image_bytes: Optional[bytes] = None
    if profile_imageb64 is not None:
        profile_image_bytes = base64.b64decode(profile_imageb64)

    user = session.query(UserModel).filter(UserModel.user_id == user_id).first()
    if user:
        user.username = username
        if display_name is not None:
            user.display_name = display_name
        if profile_image_bytes is not None:
            user.profile_image = profile_image_bytes
    else:
        user = UserModel(
            user_id=user_id,
            username=username,
            display_name=display_name,
            profile_image=profile_image_bytes,
        )
        session.add(user)


@with_session(commit=True)
def update_user_profile(user_id: int, display_name: str, profile_imageb64: str, slot_icon_b64: Optional[str] = None, *, session: Session) -> bool:
    """Update the display name and profile image for a user."""
    import base64

    user = session.query(UserModel).filter(UserModel.user_id == user_id).first()
    if not user:
        return False

    user.display_name = display_name
    user.profile_image = base64.b64decode(profile_imageb64)
    if slot_icon_b64:
        user.slot_icon = base64.b64decode(slot_icon_b64)
        logger.info(f"Updated user profile and slot icon for user {user_id}")
    else:
        logger.info(f"Updated user profile for user {user_id} (slot icon generation failed)")

    return True


@with_session
def get_user(user_id: int, *, session: Session) -> Optional[User]:
    """Fetch a user record by ID."""
    result = session.query(UserModel).filter(UserModel.user_id == user_id).first()
    return User.from_orm(result) if result else None


@with_session
def user_exists(user_id: int, *, session: Session) -> bool:
    """Check whether a user exists in the users table."""
    return session.query(UserModel).filter(UserModel.user_id == user_id).first() is not None


@with_session
def get_all_chat_users_with_profile(chat_id: str, *, session: Session) -> List[User]:
    """Return all users enrolled in the chat with stored profile images and display names."""
    results = (
        session.query(UserModel)
        .join(ChatModel, ChatModel.user_id == UserModel.user_id)
        .filter(
            ChatModel.chat_id == str(chat_id),
            UserModel.profile_image.isnot(None),
            UserModel.display_name.isnot(None),
            func.trim(UserModel.display_name) != "",
        )
        .all()
    )
    return [User.from_orm(r) for r in results]


@with_session
def get_random_chat_user_with_profile(chat_id: str, *, session: Session) -> Optional[User]:
    """Return a random user enrolled in the chat with a stored profile image."""
    result = (
        session.query(UserModel)
        .join(ChatModel, ChatModel.user_id == UserModel.user_id)
        .filter(
            ChatModel.chat_id == str(chat_id),
            UserModel.profile_image.isnot(None),
            UserModel.display_name.isnot(None),
            func.trim(UserModel.display_name) != "",
        )
        .order_by(func.random())
        .first()
    )
    return User.from_orm(result) if result else None


@with_session(commit=True)
def add_user_to_chat(chat_id: str, user_id: int, *, session: Session) -> bool:
    """Add a user to a chat; returns True if inserted."""
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


@with_session(commit=True)
def remove_user_from_chat(chat_id: str, user_id: int, *, session: Session) -> bool:
    """Remove a user from a chat; returns True if a row was deleted."""
    deleted = (
        session.query(ChatModel)
        .filter(
            ChatModel.chat_id == str(chat_id),
            ChatModel.user_id == user_id,
        )
        .delete()
    )
    return deleted > 0


@with_session
def is_user_in_chat(chat_id: str, user_id: int, *, session: Session) -> bool:
    """Check whether a user is enrolled in a chat."""
    return (
        session.query(ChatModel)
        .filter(
            ChatModel.chat_id == str(chat_id),
            ChatModel.user_id == user_id,
        )
        .first()
        is not None
    )


@with_session
def get_all_chat_users(chat_id: str, *, session: Session) -> List[int]:
    """Get all user IDs enrolled in a specific chat."""
    chats = session.query(ChatModel.user_id).filter(ChatModel.chat_id == str(chat_id)).all()
    return [c[0] for c in chats]


@with_session
def get_chat_users_and_characters(chat_id: str, *, session: Session) -> List[Dict[str, Any]]:
    """Get all users and characters for a specific chat with id, display_name, slot_icon, and type."""
    import base64

    # Get users
    user_results = (
        session.query(
            UserModel.user_id.label("id"),
            UserModel.display_name,
            UserModel.slot_icon,
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
            CharacterModel.slot_icon,
        )
        .filter(CharacterModel.chat_id == str(chat_id))
        .all()
    )

    all_items = []
    for row in user_results:
        slot_icon_b64 = base64.b64encode(row.slot_icon).decode("utf-8") if row.slot_icon else None
        all_items.append(
            {
                "id": row.id,
                "display_name": row.display_name,
                "slot_icon_b64": slot_icon_b64,
                "type": "user",
            }
        )
    for row in char_results:
        slot_icon_b64 = base64.b64encode(row.slot_icon).decode("utf-8") if row.slot_icon else None
        all_items.append(
            {
                "id": row.id,
                "display_name": row.display_name,
                "slot_icon_b64": slot_icon_b64,
                "type": "character",
            }
        )

    return all_items
