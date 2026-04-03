"""Card repository for database access to gacha cards.

This module provides data access functions for creating, retrieving,
updating, and deleting cards.
"""

from __future__ import annotations

import base64
import datetime
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session, joinedload, noload

from settings.constants import CURRENT_SEASON
from utils.image import ImageUtil
from utils.models import AspectDefinitionModel, CardImageModel, CardModel, CardAspectModel, OwnedAspectModel
from utils.schemas import Card, CardWithImage
from utils.session import with_session

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


@with_session(commit=True)
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
    description: Optional[str] = None,
    *,
    session: Session,
) -> int:
    """Add a new card to the database.

    Args:
        base_name: The base name for the card.
        modifier: The modifier for the card (nullable string).
        rarity: The rarity of the card.
        image_b64: Base64-encoded image data.
        chat_id: The chat ID where the card was created.
        source_type: The source type (e.g., "user", "character").
        source_id: The source ID.
        set_id: Optional set ID for the modifier set.
        season_id: The season this card belongs to. Defaults to CURRENT_SEASON.
        description: Optional user-provided description for unique cards.

    Returns:
        int: The card ID of the newly created card
    """
    if season_id is None:
        season_id = CURRENT_SEASON
    now = datetime.datetime.now(datetime.timezone.utc)
    if chat_id is not None:
        chat_id = str(chat_id)

    image_data: Optional[bytes] = None
    thumb_data: Optional[bytes] = None
    if image_b64:
        try:
            image_data = base64.b64decode(image_b64)
            thumb_data = ImageUtil.compress_to_fraction(image_data, scale_factor=1 / 4)
        except Exception as exc:
            logger.warning("Failed to generate thumbnail for new card: %s", exc)

    # Create card model
    card = CardModel(
        base_name=base_name,
        modifier=modifier,
        rarity=rarity,
        chat_id=chat_id,
        created_at=now,
        updated_at=now,
        source_type=source_type,
        source_id=source_id,
        set_id=set_id,
        season_id=season_id,
        description=description,
    )
    session.add(card)
    session.flush()  # Get the card ID

    # Create associated image record if available
    if image_data or thumb_data:
        card_image = CardImageModel(
            card_id=card.id,
            image=image_data,
            thumbnail=thumb_data,
            image_updated_at=now,
        )
        session.add(card_image)

    return card.id


@with_session(commit=True)
def add_card_from_generated(generated_card, chat_id: Optional[str], *, session: Session) -> int:
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
        description=getattr(generated_card, "description", None),
        session=session,
    )


@with_session
def get_user_collection(user_id: int, chat_id: Optional[str] = None, *, session: Session) -> List[Card]:
    """Get all cards owned by a user (by user_id), optionally scoped to a chat.

    Only returns cards from the current season.

    Returns:
        List[Card]: List of Card DTOs owned by the user
    """
    from repos.user_repo import get_username_for_user_id

    username = get_username_for_user_id(user_id)

    # Build owner conditions (user_id OR owner matches)
    owner_conditions = [CardModel.user_id == user_id]
    if username:
        owner_conditions.append(func.lower(CardModel.owner) == func.lower(username))

    query = (
        session.query(CardModel)
        .options(
            noload(CardModel.image),
            joinedload(CardModel.card_set),
            joinedload(CardModel.equipped_aspects)
            .joinedload(CardAspectModel.aspect)
            .joinedload(OwnedAspectModel.aspect_definition)
            .joinedload(AspectDefinitionModel.aspect_set),
        )
        .filter(
            or_(*owner_conditions),
            CardModel.season_id == CURRENT_SEASON,
        )
    )

    if chat_id is not None:
        query = query.filter(CardModel.chat_id == str(chat_id))

    query = query.order_by(_build_rarity_order_case(), CardModel.base_name, CardModel.modifier)

    return [Card.from_orm(c) for c in query.all()]


@with_session
def get_user_card_count(user_id: int, chat_id: Optional[str] = None, *, session: Session) -> int:
    """Get count of cards owned by a user (by user_id), optionally scoped to a chat.

    Only counts cards from the current season.
    """
    from repos.user_repo import get_username_for_user_id

    username = get_username_for_user_id(user_id)

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


@with_session
def get_user_card_rarity_counts(user_id: int, chat_id: Optional[str] = None, *, session: Session) -> Dict[str, int]:
    """Get counts by rarity for cards owned by a user, optionally scoped to a chat.

    Only counts cards from the current season.
    """
    from repos.user_repo import get_username_for_user_id

    username = get_username_for_user_id(user_id)
    rarities = ["Unique", "Legendary", "Epic", "Rare", "Common"]

    owner_conditions = [CardModel.user_id == user_id]
    if username:
        owner_conditions.append(func.lower(CardModel.owner) == func.lower(username))

    query = (
        session.query(CardModel.rarity, func.count(CardModel.id))
        .filter(
            or_(*owner_conditions),
            CardModel.season_id == CURRENT_SEASON,
        )
        .group_by(CardModel.rarity)
    )

    if chat_id is not None:
        query = query.filter(CardModel.chat_id == str(chat_id))

    rows = query.all()

    rarity_counts: Dict[str, int] = {rarity: 0 for rarity in rarities}
    for rarity, count in rows:
        if rarity in rarity_counts:
            rarity_counts[rarity] = count

    return rarity_counts


@with_session
def get_user_cards_by_rarity(
    user_id: int,
    username: Optional[str],
    rarity: str,
    chat_id: Optional[str] = None,
    limit: Optional[int] = None,
    unlocked: bool = False,
    *,
    session: Session,
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

    query = (
        session.query(CardModel)
        .options(
            noload(CardModel.image),
            joinedload(CardModel.card_set),
            joinedload(CardModel.equipped_aspects)
            .joinedload(CardAspectModel.aspect)
            .joinedload(OwnedAspectModel.aspect_definition)
            .joinedload(AspectDefinitionModel.aspect_set),
        )
        .filter(
            or_(*owner_conditions),
            CardModel.rarity == rarity,
            CardModel.season_id == CURRENT_SEASON,
        )
    )

    if chat_id is not None:
        query = query.filter(CardModel.chat_id == str(chat_id))

    if unlocked:
        query = query.filter(CardModel.locked == False)

    query = query.order_by(CardModel.created_at.asc().nulls_first(), CardModel.id)

    if limit is not None:
        query = query.limit(limit)

    return [Card.from_orm(c) for c in query.all()]


@with_session
def get_all_cards(chat_id: Optional[str] = None, *, session: Session) -> List[Card]:
    """Get all cards that have an owner, optionally filtered by chat.

    Only returns cards from the current season.
    """
    query = (
        session.query(CardModel)
        .options(
            noload(CardModel.image),
            joinedload(CardModel.card_set),
            joinedload(CardModel.equipped_aspects)
            .joinedload(CardAspectModel.aspect)
            .joinedload(OwnedAspectModel.aspect_definition)
            .joinedload(AspectDefinitionModel.aspect_set),
        )
        .filter(
            CardModel.owner.isnot(None),
            CardModel.season_id == CURRENT_SEASON,
        )
    )

    if chat_id is not None:
        query = query.filter(CardModel.chat_id == str(chat_id))

    query = query.order_by(_build_rarity_order_case(), CardModel.base_name, CardModel.modifier)

    return [Card.from_orm(c) for c in query.all()]


@with_session
def get_card(card_id: int, *, session: Session) -> Optional[CardWithImage]:
    """Get a card by its ID.

    Only returns cards from the current season.

    Args:
        card_id: The ID of the card to retrieve.

    Returns:
        CardWithImage if found, None otherwise.
    """
    card_orm = (
        session.query(CardModel)
        .options(
            joinedload(CardModel.image),
            joinedload(CardModel.card_set),
            joinedload(CardModel.equipped_aspects)
            .joinedload(CardAspectModel.aspect)
            .joinedload(OwnedAspectModel.aspect_definition)
            .joinedload(AspectDefinitionModel.aspect_set),
        )
        .filter(
            CardModel.id == card_id,
            CardModel.season_id == CURRENT_SEASON,
        )
        .first()
    )
    return CardWithImage.from_orm(card_orm) if card_orm else None


@with_session
def get_card_with_aspects(card_id: int, *, session: Session) -> Optional[CardWithImage]:
    """Get a card by its ID with equipped aspects eagerly loaded.

    Only returns cards from the current season.
    """
    card_orm = (
        session.query(CardModel)
        .options(
            joinedload(CardModel.image),
            joinedload(CardModel.card_set),
            joinedload(CardModel.equipped_aspects)
            .joinedload(CardAspectModel.aspect)
            .joinedload(OwnedAspectModel.aspect_definition)
            .joinedload(AspectDefinitionModel.aspect_set),
        )
        .filter(
            CardModel.id == card_id,
            CardModel.season_id == CURRENT_SEASON,
        )
        .first()
    )
    return CardWithImage.from_orm(card_orm) if card_orm else None


@with_session
def get_card_image(card_id: int, *, session: Session) -> str | None:
    """Get the base64 encoded image for a card.

    Only returns images for cards in the current season.

    Args:
        card_id: The ID of the card.

    Returns:
        Base64 encoded image string, or None if not found or wrong season.
    """
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
    if not card_image or not card_image.image:
        return None
    return base64.b64encode(card_image.image).decode("utf-8")


@with_session(commit=True)
def get_card_thumbnail(card_id: int, *, session: Session) -> str | None:
    """Get the thumbnail base64 image for a single card, generating it if missing.

    Only returns images for cards in the current season.
    Returns the 1/4-scale thumbnail (much smaller than the full image).

    Args:
        card_id: The ID of the card.

    Returns:
        Base64 encoded thumbnail string, or None if not found or wrong season.
    """
    # Verify card exists and is in the current season
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
    if not card_image:
        return None

    # Return cached thumbnail if available
    if card_image.thumbnail:
        return base64.b64encode(card_image.thumbnail).decode("utf-8")

    # Generate thumbnail from full image on-the-fly
    if not card_image.image:
        return None

    try:
        thumb_bytes = ImageUtil.compress_to_fraction(card_image.image, scale_factor=1 / 4)
        card_image.thumbnail = thumb_bytes
        return base64.b64encode(thumb_bytes).decode("utf-8")
    except Exception as exc:
        logger.warning("Failed to generate thumbnail for card %s: %s", card_id, exc)
        return base64.b64encode(card_image.image).decode("utf-8")  # Fall back to full image


@with_session(commit=True)
def get_card_images_batch(card_ids: List[int], *, session: Session) -> dict[int, str]:
    """Get thumbnail base64 images for multiple cards, generating them when missing.

    Only returns images for cards in the current season.

    Args:
        card_ids: List of card IDs to fetch images for.

    Returns:
        Dictionary mapping card_id to thumbnail base64 string.
    """
    if not card_ids:
        return {}

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
        thumb = card_image.thumbnail
        full = card_image.image

        if thumb:
            fetched[cid] = base64.b64encode(thumb).decode("utf-8")
            continue

        if not full:
            continue

        try:
            thumb_bytes = ImageUtil.compress_to_fraction(full, scale_factor=1 / 4)
            card_image.thumbnail = thumb_bytes
            fetched[cid] = base64.b64encode(thumb_bytes).decode("utf-8")
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


@with_session
def get_total_cards_count(*, session: Session) -> int:
    """Get the total number of cards owned in the current season."""
    count = (
        session.query(func.count(CardModel.id))
        .filter(
            CardModel.owner.isnot(None),
            CardModel.season_id == CURRENT_SEASON,
        )
        .scalar()
    )
    return count or 0


@with_session
def get_random_card_summaries(chat_id: str, count: int, *, session: Session) -> List[Dict[str, Any]]:
    """Get random card summaries (id, rarity, title) from a chat without loading images.

    This is a lightweight query optimized for RTB game creation — it only fetches
    the minimal columns needed (id, base_name, modifier, rarity) and avoids
    loading image data or full ORM objects.

    Args:
        chat_id: The chat ID to select cards from.
        count: Number of random cards to select.

    Returns:
        List of dicts with keys: id, base_name, modifier, rarity.
        Empty list if not enough cards are available.
    """
    rows = (
        session.query(
            CardModel.id,
            CardModel.base_name,
            CardModel.modifier,
            CardModel.rarity,
        )
        .filter(
            CardModel.owner.isnot(None),
            CardModel.chat_id == str(chat_id),
            CardModel.season_id == CURRENT_SEASON,
        )
        .all()
    )

    if len(rows) < count:
        return []

    import random as _random

    selected = _random.sample(rows, count)
    return [
        {
            "id": row[0],
            "base_name": row[1],
            "modifier": row[2],
            "rarity": row[3],
        }
        for row in selected
    ]


@with_session
def get_chat_card_rarity_counts(chat_id: str, *, session: Session) -> Dict[str, int]:
    """Get counts of cards per rarity in a chat for the current season.

    Lightweight query for checking game availability (e.g., RTB).

    Args:
        chat_id: The chat ID to check.

    Returns:
        Dictionary mapping rarity to count.
    """
    rows = (
        session.query(CardModel.rarity, func.count(CardModel.id))
        .filter(
            CardModel.owner.isnot(None),
            CardModel.chat_id == str(chat_id),
            CardModel.season_id == CURRENT_SEASON,
        )
        .group_by(CardModel.rarity)
        .all()
    )
    return {rarity: cnt for rarity, cnt in rows}


@with_session
def get_user_stats(username, *, session: Session):
    """Get card statistics for a user in the current season."""
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


@with_session
def get_all_users_with_cards(chat_id: Optional[str] = None, *, session: Session):
    """Get all unique users who have claimed cards in the current season, optionally scoped to a chat."""
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


@with_session(commit=True)
def swap_card_owners(card_id1, card_id2, *, session: Session) -> bool:
    """Swap the owners of two cards.

    Only works for cards in the current season.
    """
    try:
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


@with_session(commit=True)
def set_card_owner(
    card_id: int, owner: str, user_id: Optional[int] = None, *, updated_at=None, session: Session
) -> bool:
    """Set the owner and optional user_id for a card without affecting claim balances.

    Only works for cards in the current season.
    """
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
    if updated_at is not None:
        card.updated_at = updated_at
    return True


@with_session(commit=True)
def update_card_file_id(card_id: int, file_id: str, *, session: Session) -> bool:
    """Update the Telegram file_id for a card.

    Only works for cards in the current season.

    Returns:
        bool: True if the card was found and updated, False otherwise.
    """
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


@with_session(commit=True)
def update_card_image(card_id: int, image_b64: str, *, session: Session) -> bool:
    """Update the image for a card, regenerating thumbnail and clearing file_id.

    Only works for cards in the current season.

    Returns:
        bool: True if the card was found and updated, False otherwise.
    """
    # Check if card exists and is in current season
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
    image_data: Optional[bytes] = None
    thumb_data: Optional[bytes] = None
    if image_b64:
        try:
            image_data = base64.b64decode(image_b64)
            thumb_data = ImageUtil.compress_to_fraction(image_data, scale_factor=1 / 4)
        except Exception as exc:
            logger.warning("Failed to generate thumbnail for refreshed card %s: %s", card_id, exc)

    now = datetime.datetime.now(datetime.timezone.utc)
    # Update or create card_images record
    card_image = session.query(CardImageModel).filter(CardImageModel.card_id == card_id).first()
    if card_image:
        card_image.image = image_data
        card_image.thumbnail = thumb_data
        card_image.image_updated_at = now
    else:
        card_image = CardImageModel(
            card_id=card_id,
            image=image_data,
            thumbnail=thumb_data,
            image_updated_at=now,
        )
        session.add(card_image)

    # Clear file_id since we have a new image
    card.file_id = None
    card.updated_at = now

    logger.info(f"Updated image for card {card_id}, cleared file_id")
    return True


@with_session(commit=True)
def set_card_locked(card_id: int, is_locked: bool, *, session: Session) -> bool:
    """Set the locked status for a card.

    Only works for cards in the current season.

    Returns:
        bool: True if the card was found and updated, False otherwise.
    """
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
    card.updated_at = datetime.datetime.now(datetime.timezone.utc)
    logger.info(f"Set locked={is_locked} for card {card_id}: True")
    return True


@with_session(commit=True)
def clear_all_file_ids(*, session: Session):
    """Clear all file_ids from all cards (set to NULL)."""
    affected_rows = session.query(CardModel).update({CardModel.file_id: None})
    logger.info(f"Cleared file_ids for {affected_rows} cards")
    return affected_rows


@with_session(commit=True)
def nullify_card_owner(card_id, *, session: Session) -> bool:
    """Set card owner to NULL (for rerolls/burns) instead of deleting.

    Only works for cards in the current season.
    """
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


@with_session(commit=True)
def delete_card(card_id, *, session: Session) -> bool:
    """Delete a card from the database (use sparingly - prefer nullify_card_owner).

    Only works for cards in the current season.
    """
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


@with_session(commit=True)
def delete_cards(card_ids: List[int], *, session: Session) -> int:
    """Delete multiple cards by ID. Returns number of deleted cards.

    Only works for cards in the current season. Equipped aspects are also
    destroyed alongside their card_aspects junction rows.
    """
    if not card_ids:
        return 0

    # Collect equipped aspect IDs before removing junction rows
    equipped_aspect_ids = [
        row.aspect_id
        for row in session.query(CardAspectModel.aspect_id).filter(
            CardAspectModel.card_id.in_(card_ids)
        ).all()
    ]

    # Delete junction rows first to satisfy FK constraint
    session.query(CardAspectModel).filter(
        CardAspectModel.card_id.in_(card_ids)
    ).delete(synchronize_session=False)

    # Delete the owned aspect instances that were equipped on these cards
    if equipped_aspect_ids:
        session.query(OwnedAspectModel).filter(
            OwnedAspectModel.id.in_(equipped_aspect_ids)
        ).delete(synchronize_session=False)

    deleted = (
        session.query(CardModel)
        .filter(
            CardModel.id.in_(card_ids),
            CardModel.season_id == CURRENT_SEASON,
        )
        .delete(synchronize_session=False)
    )
    return deleted



@with_session
def get_unclaimed_card_for_update(card_id: int, *, session: Session) -> Optional[Card]:
    """Get an unclaimed current-season card with row lock."""
    card_orm = (
        session.query(CardModel)
        .options(noload("*"))
        .filter(
            CardModel.id == card_id,
            CardModel.owner.is_(None),
            CardModel.season_id == CURRENT_SEASON,
        )
        .with_for_update()
        .first()
    )
    return Card.from_orm(card_orm) if card_orm else None


@with_session
def get_card_for_update(card_id: int, *, session: Session) -> Optional[Card]:
    """Get a current-season card with row lock."""
    card_orm = (
        session.query(CardModel)
        .options(noload("*"))
        .filter(
            CardModel.id == card_id,
            CardModel.season_id == CURRENT_SEASON,
        )
        .with_for_update()
        .first()
    )
    return Card.from_orm(card_orm) if card_orm else None


@with_session(commit=True)
def update_card_aspect_equip(
    card_id: int,
    *,
    aspect_count: int,
    modifier: str,
    updated_at,
    session: Session,
) -> bool:
    """Update card fields after equipping an aspect."""
    card = session.query(CardModel).filter(CardModel.id == card_id).first()
    if not card:
        return False
    card.aspect_count = aspect_count
    card.modifier = modifier
    card.updated_at = updated_at
    return True
