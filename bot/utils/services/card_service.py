"""Card service for managing gacha cards.

This module provides all card-related business logic including
creating, retrieving, updating, and deleting cards.
"""

from __future__ import annotations

import base64
import datetime
import logging
from typing import Dict, List, Optional

from sqlalchemy import case, func, or_
from sqlalchemy.orm import joinedload

from settings.constants import CURRENT_SEASON
from utils.image import ImageUtil
from utils.models import CardImageModel, CardModel
from utils.schemas import Card, CardWithImage
from utils.session import get_session

logger = logging.getLogger(__name__)


def _build_rarity_order_case():
    """Build a CASE expression for ordering by rarity."""
    return case(
        (CardModel.rarity == "Unique", 1),
        (CardModel.rarity == "Legendary", 2),
        (CardModel.rarity == "Epic", 3),
        (CardModel.rarity == "Rare", 4),
        else_=5,
    )


def add_card(
    base_name: str,
    modifier: str,
    rarity: str,
    image_b64: str,
    chat_id: Optional[str],
    source_type: str,
    source_id: int,
    set_id: Optional[int] = None,
    season_id: Optional[int] = None,
) -> int:
    """Add a new card to the database.

    Args:
        base_name: The base name for the card.
        modifier: The modifier for the card.
        rarity: The rarity of the card.
        image_b64: Base64-encoded image data.
        chat_id: The chat ID where the card was created.
        source_type: The source type (e.g., "user", "character").
        source_id: The source ID.
        set_id: Optional set ID for the modifier set.
        season_id: The season this card belongs to. Defaults to CURRENT_SEASON.

    Returns:
        int: The card ID of the newly created card
    """
    if season_id is None:
        season_id = CURRENT_SEASON
    now = datetime.datetime.now().isoformat()
    if chat_id is not None:
        chat_id = str(chat_id)

    image_thumb_b64: Optional[str] = None
    if image_b64:
        try:
            image_bytes = base64.b64decode(image_b64)
            thumb_bytes = ImageUtil.compress_to_fraction(image_bytes, scale_factor=1 / 4)
            image_thumb_b64 = base64.b64encode(thumb_bytes).decode("utf-8")
        except Exception as exc:
            logger.warning("Failed to generate thumbnail for new card: %s", exc)

    with get_session(commit=True) as session:
        # Create card model
        card = CardModel(
            base_name=base_name,
            modifier=modifier,
            rarity=rarity,
            chat_id=chat_id,
            created_at=now,
            source_type=source_type,
            source_id=source_id,
            set_id=set_id,
            season_id=season_id,
        )
        session.add(card)
        session.flush()  # Get the card ID

        # Create associated image record if available
        if image_b64 or image_thumb_b64:
            card_image = CardImageModel(
                card_id=card.id,
                image_b64=image_b64,
                image_thumb_b64=image_thumb_b64,
            )
            session.add(card_image)

        return card.id


def add_card_from_generated(generated_card, chat_id: Optional[str]) -> int:
    """
    Add a card to the database from a GeneratedCard object.

    This is a convenience wrapper around add_card that accepts a GeneratedCard
    (from utils.rolling) and extracts all the necessary fields.

    Args:
        generated_card: A GeneratedCard instance from utils.rolling
        chat_id: The chat ID to associate with this card

    Returns:
        int: The database ID of the newly created card
    """
    return add_card(
        base_name=generated_card.base_name,
        modifier=generated_card.modifier,
        rarity=generated_card.rarity,
        image_b64=generated_card.image_b64,
        chat_id=chat_id,
        source_type=generated_card.source_type,
        source_id=generated_card.source_id,
        set_id=generated_card.set_id,
    )


def try_claim_card(card_id: int, owner: str, user_id: Optional[int] = None) -> bool:
    """Attempt to claim a card for a user without touching claim balances.

    Only works for cards in the current season.
    """
    with get_session(commit=True) as session:
        card = (
            session.query(CardModel)
            .filter(
                CardModel.id == card_id,
                CardModel.owner.is_(None),
                CardModel.season_id == CURRENT_SEASON,
            )
            .first()
        )

        if card is None:
            return False

        card.owner = owner
        if user_id is not None:
            card.user_id = user_id
        return True


def get_user_collection(user_id: int, chat_id: Optional[str] = None) -> List[Card]:
    """Get all cards owned by a user (by user_id), optionally scoped to a chat.

    Only returns cards from the current season.

    Returns:
        List[Card]: List of Card objects owned by the user
    """
    # Import here to avoid circular dependency
    from utils.services.user_service import get_username_for_user_id

    username = get_username_for_user_id(user_id)

    with get_session() as session:
        # Build owner conditions (user_id OR owner matches)
        owner_conditions = [CardModel.user_id == user_id]
        if username:
            owner_conditions.append(func.lower(CardModel.owner) == func.lower(username))

        query = session.query(CardModel).filter(
            or_(*owner_conditions),
            CardModel.season_id == CURRENT_SEASON,
        )

        if chat_id is not None:
            query = query.filter(CardModel.chat_id == str(chat_id))

        query = query.order_by(_build_rarity_order_case(), CardModel.base_name, CardModel.modifier)

        return [Card.from_orm(card) for card in query.all()]


def get_user_card_count(user_id: int, chat_id: Optional[str] = None) -> int:
    """Get count of cards owned by a user (by user_id), optionally scoped to a chat.

    Only counts cards from the current season.
    """
    # Import here to avoid circular dependency
    from utils.services.user_service import get_username_for_user_id

    username = get_username_for_user_id(user_id)

    with get_session() as session:
        owner_conditions = [CardModel.user_id == user_id]
        if username:
            owner_conditions.append(func.lower(CardModel.owner) == func.lower(username))

        query = session.query(func.count(CardModel.id)).filter(
            or_(*owner_conditions),
            CardModel.season_id == CURRENT_SEASON,
        )

        if chat_id is not None:
            query = query.filter(CardModel.chat_id == str(chat_id))

        return query.scalar() or 0


def get_user_cards_by_rarity(
    user_id: int,
    username: Optional[str],
    rarity: str,
    chat_id: Optional[str] = None,
    limit: Optional[int] = None,
    unlocked: bool = False,
) -> List[Card]:
    """Return cards owned by the user for a specific rarity, optionally limited in count.

    Only returns cards from the current season.
    """
    owner_conditions = []

    if user_id is not None:
        owner_conditions.append(CardModel.user_id == user_id)

    if username:
        owner_conditions.append(func.lower(CardModel.owner) == func.lower(username))

    if not owner_conditions:
        return []

    with get_session() as session:
        query = session.query(CardModel).filter(
            or_(*owner_conditions),
            CardModel.rarity == rarity,
            CardModel.season_id == CURRENT_SEASON,
        )

        if chat_id is not None:
            query = query.filter(CardModel.chat_id == str(chat_id))

        if unlocked:
            query = query.filter(CardModel.locked == False)

        query = query.order_by(func.coalesce(CardModel.created_at, ""), CardModel.id)

        if limit is not None:
            query = query.limit(limit)

        return [Card.from_orm(card) for card in query.all()]


def get_all_cards(chat_id: Optional[str] = None) -> List[Card]:
    """Get all cards that have an owner, optionally filtered by chat.

    Only returns cards from the current season.
    """
    with get_session() as session:
        query = session.query(CardModel).filter(
            CardModel.owner.isnot(None),
            CardModel.season_id == CURRENT_SEASON,
        )

        if chat_id is not None:
            query = query.filter(CardModel.chat_id == str(chat_id))

        query = query.order_by(_build_rarity_order_case(), CardModel.base_name, CardModel.modifier)

        return [Card.from_orm(card) for card in query.all()]


def get_card(card_id: int) -> Optional[CardWithImage]:
    """Get a card by its ID.

    Only returns cards from the current season.

    Args:
        card_id: The ID of the card to retrieve.

    Returns:
        CardWithImage if found, None otherwise.
    """
    with get_session() as session:
        card_orm = (
            session.query(CardModel)
            .options(joinedload(CardModel.image))
            .filter(
                CardModel.id == card_id,
                CardModel.season_id == CURRENT_SEASON,
            )
            .first()
        )
        if card_orm is None:
            return None
        return CardWithImage.from_orm(card_orm)


def get_card_image(card_id: int) -> str | None:
    """Get the base64 encoded image for a card.

    Only returns images for cards in the current season.

    Args:
        card_id: The ID of the card.

    Returns:
        Base64 encoded image string, or None if not found or wrong season.
    """
    with get_session() as session:
        # First verify the card exists and is in the current season
        card = (
            session.query(CardModel)
            .filter(
                CardModel.id == card_id,
                CardModel.season_id == CURRENT_SEASON,
            )
            .first()
        )

        if not card:
            return None

        card_image = session.query(CardImageModel).filter(CardImageModel.card_id == card_id).first()
        return card_image.image_b64 if card_image else None


def get_card_images_batch(card_ids: List[int]) -> dict[int, str]:
    """Get thumbnail base64 images for multiple cards, generating them when missing.

    Only returns images for cards in the current season.

    Args:
        card_ids: List of card IDs to fetch images for.

    Returns:
        Dictionary mapping card_id to thumbnail base64 string.
    """
    if not card_ids:
        return {}

    with get_session(commit=True) as session:
        # First filter to only cards in the current season
        valid_card_ids = {
            row[0]
            for row in session.query(CardModel.id)
            .filter(
                CardModel.id.in_(card_ids),
                CardModel.season_id == CURRENT_SEASON,
            )
            .all()
        }

        if not valid_card_ids:
            return {}

        card_images = (
            session.query(CardImageModel).filter(CardImageModel.card_id.in_(valid_card_ids)).all()
        )

        fetched: dict[int, str] = {}
        for card_image in card_images:
            cid = card_image.card_id
            thumb = card_image.image_thumb_b64
            full = card_image.image_b64

            if thumb:
                fetched[cid] = thumb
                continue

            if not full:
                continue

            try:
                image_bytes = base64.b64decode(full)
                thumb_bytes = ImageUtil.compress_to_fraction(image_bytes, scale_factor=1 / 4)
                thumb_b64 = base64.b64encode(thumb_bytes).decode("utf-8")
                card_image.image_thumb_b64 = thumb_b64
                fetched[cid] = thumb_b64
            except Exception as exc:
                logger.warning(
                    "Failed to generate thumbnail during batch fetch for card %s: %s",
                    cid,
                    exc,
                )

        # Return in original order
        ordered: dict[int, str] = {}
        for cid in card_ids:
            image = fetched.get(cid)
            if image is not None:
                ordered[cid] = image
        return ordered


def get_total_cards_count() -> int:
    """Get the total number of cards owned in the current season."""
    with get_session() as session:
        count = (
            session.query(func.count(CardModel.id))
            .filter(
                CardModel.owner.isnot(None),
                CardModel.season_id == CURRENT_SEASON,
            )
            .scalar()
        )
        return count or 0


def get_user_stats(username):
    """Get card statistics for a user in the current season."""
    with get_session() as session:
        owned_count = (
            session.query(func.count(CardModel.id))
            .filter(
                CardModel.owner == username,
                CardModel.season_id == CURRENT_SEASON,
            )
            .scalar()
            or 0
        )

        rarities = ["Unique", "Legendary", "Epic", "Rare", "Common"]
        rarity_counts = {}
        for rarity in rarities:
            count = (
                session.query(func.count(CardModel.id))
                .filter(
                    CardModel.owner == username,
                    CardModel.rarity == rarity,
                    CardModel.season_id == CURRENT_SEASON,
                )
                .scalar()
                or 0
            )
            rarity_counts[rarity] = count

    total_count = get_total_cards_count()

    return {"owned": owned_count, "total": total_count, "rarities": rarity_counts}


def get_all_users_with_cards(chat_id: Optional[str] = None):
    """Get all unique users who have claimed cards in the current season, optionally scoped to a chat."""
    with get_session() as session:
        query = (
            session.query(CardModel.owner)
            .filter(
                CardModel.owner.isnot(None),
                CardModel.season_id == CURRENT_SEASON,
            )
            .distinct()
        )

        if chat_id is not None:
            query = query.filter(CardModel.chat_id == str(chat_id))

        query = query.order_by(CardModel.owner)
        return [row[0] for row in query.all()]


def swap_card_owners(card_id1, card_id2) -> bool:
    """Swap the owners of two cards.

    Only works for cards in the current season.
    """
    try:
        with get_session(commit=True) as session:
            card1 = (
                session.query(CardModel)
                .filter(
                    CardModel.id == card_id1,
                    CardModel.season_id == CURRENT_SEASON,
                )
                .first()
            )
            if not card1:
                return False

            card2 = (
                session.query(CardModel)
                .filter(
                    CardModel.id == card_id2,
                    CardModel.season_id == CURRENT_SEASON,
                )
                .first()
            )
            if not card2:
                return False

            # Swap owners and user_ids
            card1.owner, card2.owner = card2.owner, card1.owner
            card1.user_id, card2.user_id = card2.user_id, card1.user_id
            return True
    except Exception:
        return False


def set_card_owner(card_id: int, owner: str, user_id: Optional[int] = None) -> bool:
    """Set the owner and optional user_id for a card without affecting claim balances.

    Only works for cards in the current season.
    """
    with get_session(commit=True) as session:
        card = (
            session.query(CardModel)
            .filter(
                CardModel.id == card_id,
                CardModel.season_id == CURRENT_SEASON,
            )
            .first()
        )
        if not card:
            return False
        card.owner = owner
        card.user_id = user_id
        return True


def update_card_file_id(card_id: int, file_id: str) -> bool:
    """Update the Telegram file_id for a card.

    Only works for cards in the current season.

    Returns:
        bool: True if the card was found and updated, False otherwise.
    """
    with get_session(commit=True) as session:
        card = (
            session.query(CardModel)
            .filter(
                CardModel.id == card_id,
                CardModel.season_id == CURRENT_SEASON,
            )
            .first()
        )
        if not card:
            logger.info(f"Updated file_id for card {card_id}: False (not found or wrong season)")
            return False
        card.file_id = file_id
    logger.info(f"Updated file_id for card {card_id}: {file_id}")
    return True


def update_card_image(card_id: int, image_b64: str) -> bool:
    """Update the image for a card, regenerating thumbnail and clearing file_id.

    Only works for cards in the current season.

    Returns:
        bool: True if the card was found and updated, False otherwise.
    """
    # First check if card exists and is in current season
    with get_session() as session:
        card = (
            session.query(CardModel)
            .filter(
                CardModel.id == card_id,
                CardModel.season_id == CURRENT_SEASON,
            )
            .first()
        )
        if not card:
            logger.info(f"Update image for card {card_id}: False (not found or wrong season)")
            return False

    # Generate new thumbnail
    image_thumb_b64: Optional[str] = None
    if image_b64:
        try:
            image_bytes = base64.b64decode(image_b64)
            thumb_bytes = ImageUtil.compress_to_fraction(image_bytes, scale_factor=1 / 4)
            image_thumb_b64 = base64.b64encode(thumb_bytes).decode("utf-8")
        except Exception as exc:
            logger.warning("Failed to generate thumbnail for refreshed card %s: %s", card_id, exc)

    with get_session(commit=True) as session:
        # Update or create card_images record
        card_image = session.query(CardImageModel).filter(CardImageModel.card_id == card_id).first()
        if card_image:
            card_image.image_b64 = image_b64
            card_image.image_thumb_b64 = image_thumb_b64
        else:
            card_image = CardImageModel(
                card_id=card_id,
                image_b64=image_b64,
                image_thumb_b64=image_thumb_b64,
            )
            session.add(card_image)

        # Clear file_id since we have a new image
        card = session.query(CardModel).filter(CardModel.id == card_id).first()
        if card:
            card.file_id = None

    logger.info(f"Updated image for card {card_id}, cleared file_id")
    return True


def set_card_locked(card_id: int, is_locked: bool) -> bool:
    """Set the locked status for a card.

    Only works for cards in the current season.

    Returns:
        bool: True if the card was found and updated, False otherwise.
    """
    with get_session(commit=True) as session:
        card = (
            session.query(CardModel)
            .filter(
                CardModel.id == card_id,
                CardModel.season_id == CURRENT_SEASON,
            )
            .first()
        )
        if not card:
            logger.info(
                f"Set locked={is_locked} for card {card_id}: False (not found or wrong season)"
            )
            return False
        card.locked = is_locked
    logger.info(f"Set locked={is_locked} for card {card_id}: True")
    return True


def clear_all_file_ids():
    """Clear all file_ids from all cards (set to NULL)."""
    with get_session(commit=True) as session:
        affected_rows = session.query(CardModel).update({CardModel.file_id: None})
    logger.info(f"Cleared file_ids for {affected_rows} cards")
    return affected_rows


def nullify_card_owner(card_id) -> bool:
    """Set card owner to NULL (for rerolls/burns) instead of deleting.

    Only works for cards in the current season.
    """
    with get_session(commit=True) as session:
        card = (
            session.query(CardModel)
            .filter(
                CardModel.id == card_id,
                CardModel.season_id == CURRENT_SEASON,
            )
            .first()
        )
        if not card:
            logger.info(f"Nullified owner for card {card_id}: False (not found or wrong season)")
            return False
        card.owner = None
        card.user_id = None
    logger.info(f"Nullified owner for card {card_id}: True")
    return True


def delete_card(card_id) -> bool:
    """Delete a card from the database (use sparingly - prefer nullify_card_owner).

    Only works for cards in the current season.
    """
    with get_session(commit=True) as session:
        deleted = (
            session.query(CardModel)
            .filter(
                CardModel.id == card_id,
                CardModel.season_id == CURRENT_SEASON,
            )
            .delete()
        )
    logger.info(f"Deleted card {card_id}: {deleted > 0}")
    return deleted > 0


def get_modifier_counts_for_chat(chat_id: str) -> Dict[str, int]:
    """Get the count of each modifier used in cards for a specific chat in the current season.

    Args:
        chat_id: The chat ID to get modifier counts for.

    Returns:
        A dictionary mapping modifier strings to their occurrence count.
    """
    with get_session() as session:
        results = (
            session.query(CardModel.modifier, func.count(CardModel.id).label("count"))
            .filter(
                CardModel.chat_id == str(chat_id),
                CardModel.season_id == CURRENT_SEASON,
            )
            .group_by(CardModel.modifier)
            .all()
        )
        return {row[0]: row[1] for row in results if row[0] is not None}


def get_unique_modifiers(chat_id: str) -> List[str]:
    """Get a list of modifiers used in Unique cards for a specific chat in the current season."""
    with get_session() as session:
        results = (
            session.query(CardModel.modifier)
            .filter(
                CardModel.chat_id == str(chat_id),
                CardModel.rarity == "Unique",
                CardModel.season_id == CURRENT_SEASON,
            )
            .distinct()
            .all()
        )
        return [row[0] for row in results if row[0] is not None]


def delete_cards(card_ids: List[int]) -> int:
    """Delete multiple cards by ID. Returns number of deleted cards.

    Only works for cards in the current season.
    """
    if not card_ids:
        return 0

    with get_session(commit=True) as session:
        deleted = (
            session.query(CardModel)
            .filter(
                CardModel.id.in_(card_ids),
                CardModel.season_id == CURRENT_SEASON,
            )
            .delete(synchronize_session=False)
        )
        return deleted
