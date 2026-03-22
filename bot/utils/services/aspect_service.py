"""Aspect service for managing owned aspects.

This module provides all aspect-related business logic including
creating, retrieving, claiming, locking, burning, recycling, and
equipping aspects onto cards.
"""

from __future__ import annotations

import base64
import datetime
import logging
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from settings.constants import CURRENT_SEASON, RARITY_ORDER, get_claim_cost, get_spin_reward
from utils.events import EquipOutcome, EventType
from utils.image import ImageUtil
from utils.models import (
    AspectDefinitionModel,
    AspectImageModel,
    CardAspectModel,
    CardModel,
    ClaimModel,
    OwnedAspectModel,
    SetModel,
)
from utils.schemas import AspectDefinition, CardAspect, OwnedAspect, OwnedAspectWithImage
from utils.session import get_session

logger = logging.getLogger(__name__)

# Canonical rarity order for grouping output
_RARITY_ORDER = ("Common", "Rare", "Epic", "Legendary")


# ---------------------------------------------------------------------------
# Aspect definition queries
# ---------------------------------------------------------------------------


def get_aspect_definitions_by_rarity(
    season_id: Optional[int] = None,
    source: Optional[str] = None,
    active_only: bool = True,
) -> Dict[str, List[AspectDefinition]]:
    """Return aspect definitions grouped by rarity for the given season.

    Mirrors ``modifier_service.get_modifiers_by_rarity()`` but queries
    ``AspectDefinitionModel`` instead of ``ModifierModel``.

    Args:
        season_id: Season to query. Defaults to ``CURRENT_SEASON``.
        source: Optional source filter (``"roll"``, ``"slots"``).
                Sets with ``source="all"`` always qualify.
        active_only: If True (default), only include definitions from
                     active sets.

    Returns:
        Ordered dict mapping rarity name → list of ``AspectDefinition``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session() as session:
        query = (
            session.query(AspectDefinitionModel)
            .join(
                SetModel,
                (AspectDefinitionModel.set_id == SetModel.id)
                & (AspectDefinitionModel.season_id == SetModel.season_id),
            )
            .filter(AspectDefinitionModel.season_id == season_id)
        )

        if active_only:
            query = query.filter(SetModel.active.is_(True))

        if source is not None:
            query = query.filter((SetModel.source == "all") | (SetModel.source == source))

        query = query.order_by(AspectDefinitionModel.name)
        rows = query.all()

        # Build grouped result
        grouped: Dict[str, List[AspectDefinition]] = {}
        for ad in rows:
            entry = AspectDefinition.from_orm(ad)
            grouped.setdefault(ad.rarity, []).append(entry)

    # Order by canonical rarity, then any extras alphabetically
    ordered: Dict[str, List[AspectDefinition]] = {}
    for rarity in _RARITY_ORDER:
        ordered[rarity] = grouped.pop(rarity, [])
    for rarity in sorted(grouped):
        ordered[rarity] = grouped[rarity]

    return ordered


def get_aspect_definitions_by_set(
    set_id: int,
    season_id: Optional[int] = None,
) -> List[AspectDefinitionModel]:
    """Return all aspect definitions belonging to a set.

    Args:
        set_id: The set's ID within the season.
        season_id: Season to query. Defaults to ``CURRENT_SEASON``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session() as session:
        return (
            session.query(AspectDefinitionModel)
            .filter(
                AspectDefinitionModel.set_id == set_id,
                AspectDefinitionModel.season_id == season_id,
            )
            .order_by(AspectDefinitionModel.rarity, AspectDefinitionModel.name)
            .all()
        )


def get_aspect_definition_by_id(
    definition_id: int,
) -> Optional[AspectDefinitionModel]:
    """Fetch a single aspect definition by its auto-increment ID."""
    with get_session() as session:
        return (
            session.query(AspectDefinitionModel)
            .filter(AspectDefinitionModel.id == definition_id)
            .first()
        )


def get_aspect_definition_by_name_and_set(
    name: str,
    set_id: int,
    season_id: Optional[int] = None,
) -> Optional[AspectDefinitionModel]:
    """Lookup an aspect definition by name within a specific set.

    Args:
        name: The aspect keyword (case-sensitive).
        set_id: The set ID.
        season_id: Season to query. Defaults to ``CURRENT_SEASON``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session() as session:
        return (
            session.query(AspectDefinitionModel)
            .filter(
                AspectDefinitionModel.name == name,
                AspectDefinitionModel.set_id == set_id,
                AspectDefinitionModel.season_id == season_id,
            )
            .first()
        )


def get_aspect_definition_count_per_set(
    season_id: Optional[int] = None,
) -> Dict[int, int]:
    """Return a mapping of set_id → number of aspect definitions for the season."""
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session() as session:
        rows = (
            session.query(
                AspectDefinitionModel.set_id,
                func.count(AspectDefinitionModel.id),
            )
            .filter(AspectDefinitionModel.season_id == season_id)
            .group_by(AspectDefinitionModel.set_id)
            .all()
        )
        return {set_id: count for set_id, count in rows}


def get_owned_count_for_definition(definition_id: int) -> int:
    """Return the number of owned aspect instances linked to a definition."""
    with get_session() as session:
        return (
            session.query(func.count(OwnedAspectModel.id))
            .filter(OwnedAspectModel.aspect_definition_id == definition_id)
            .scalar()
            or 0
        )


# ---------------------------------------------------------------------------
# Aspect definition CRUD
# ---------------------------------------------------------------------------


def create_aspect_definition(
    set_id: int,
    name: str,
    rarity: str,
    season_id: Optional[int] = None,
) -> AspectDefinitionModel:
    """Create a new aspect definition in the database.

    Args:
        set_id: The set this definition belongs to.
        name: The aspect keyword.
        rarity: The rarity level (Common / Rare / Epic / Legendary).
        season_id: Season ID. Defaults to ``CURRENT_SEASON``.

    Returns:
        The newly created ``AspectDefinitionModel``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    now = datetime.datetime.now(datetime.timezone.utc)

    with get_session(commit=True) as session:
        definition = AspectDefinitionModel(
            set_id=set_id,
            season_id=season_id,
            name=name,
            rarity=rarity,
            created_at=now,
        )
        session.add(definition)
        session.flush()
        logger.info(
            "Created aspect definition id=%s name='%s' rarity=%s set=%s season=%s",
            definition.id,
            name,
            rarity,
            set_id,
            season_id,
        )
        return definition


def update_aspect_definition(
    definition_id: int,
    *,
    name: Optional[str] = None,
    rarity: Optional[str] = None,
    set_id: Optional[int] = None,
) -> Optional[AspectDefinitionModel]:
    """Update an existing aspect definition's fields.

    Only provided (non-None) fields are updated.

    Returns:
        The updated ``AspectDefinitionModel``, or ``None`` if not found.
    """
    with get_session(commit=True) as session:
        definition = (
            session.query(AspectDefinitionModel)
            .filter(AspectDefinitionModel.id == definition_id)
            .first()
        )
        if not definition:
            return None

        if name is not None:
            definition.name = name
        if rarity is not None:
            definition.rarity = rarity
        if set_id is not None:
            definition.set_id = set_id

        logger.info(
            "Updated aspect definition id=%s: name=%s rarity=%s set=%s",
            definition_id,
            name,
            rarity,
            set_id,
        )
        return definition


def delete_aspect_definition(definition_id: int) -> tuple[bool, str]:
    """Delete an aspect definition if it is not linked to any owned aspects.

    Returns:
        A tuple ``(success: bool, message: str)``.
    """
    with get_session(commit=True) as session:
        definition = (
            session.query(AspectDefinitionModel)
            .filter(AspectDefinitionModel.id == definition_id)
            .first()
        )
        if not definition:
            return False, "Aspect definition not found"

        owned_count = (
            session.query(func.count(OwnedAspectModel.id))
            .filter(OwnedAspectModel.aspect_definition_id == definition_id)
            .scalar()
        )
        if owned_count and owned_count > 0:
            return (
                False,
                f"Cannot delete: definition is used by {owned_count} owned aspect(s)",
            )

        session.delete(definition)
        logger.info(
            "Deleted aspect definition id=%s name='%s'",
            definition_id,
            definition.name,
        )
        return True, "Aspect definition deleted"


def bulk_upsert_aspect_definitions(
    definitions: list[dict],
    season_id: Optional[int] = None,
) -> int:
    """Bulk insert or update aspect definitions.

    Each dict should contain at least ``set_id``, ``name``, ``rarity``.
    If a definition with the same ``(name, set_id, season_id)`` already
    exists, its rarity is updated; otherwise a new row is inserted.

    Returns:
        The number of rows inserted or updated.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    now = datetime.datetime.now(datetime.timezone.utc)
    count = 0

    with get_session(commit=True) as session:
        for def_dict in definitions:
            set_id = def_dict["set_id"]
            name = def_dict["name"]
            rarity = def_dict["rarity"]

            existing = (
                session.query(AspectDefinitionModel)
                .filter(
                    AspectDefinitionModel.name == name,
                    AspectDefinitionModel.set_id == set_id,
                    AspectDefinitionModel.season_id == season_id,
                )
                .first()
            )

            if existing:
                existing.rarity = rarity
            else:
                session.add(
                    AspectDefinitionModel(
                        set_id=set_id,
                        season_id=season_id,
                        name=name,
                        rarity=rarity,
                        created_at=now,
                    )
                )
            count += 1

    logger.info("Bulk upserted %d aspect definitions for season %s", count, season_id)
    return count


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


def get_user_aspects(
    user_id: int,
    season_id: Optional[int] = None,
    chat_id: Optional[str] = None,
    rarity: Optional[str] = None,
    unlocked_only: bool = False,
) -> List[OwnedAspect]:
    """Get all unequipped aspects owned by a user for the given season.

    "Unequipped" means the aspect has no entry in ``card_aspects``.

    Args:
        user_id: The user whose aspects to query.
        season_id: Season filter (defaults to ``CURRENT_SEASON``).
        chat_id: Optional chat filter.
        rarity: Optional rarity filter (e.g. ``"Legendary"``).
        unlocked_only: If True, exclude locked aspects.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session() as session:
        query = (
            session.query(OwnedAspectModel)
            .outerjoin(CardAspectModel, CardAspectModel.aspect_id == OwnedAspectModel.id)
            .filter(
                OwnedAspectModel.user_id == user_id,
                OwnedAspectModel.season_id == season_id,
                CardAspectModel.id.is_(None),  # unequipped only
            )
            .options(joinedload(OwnedAspectModel.aspect_definition))
        )
        if chat_id is not None:
            query = query.filter(OwnedAspectModel.chat_id == str(chat_id))
        if rarity is not None:
            query = query.filter(OwnedAspectModel.rarity == rarity)
        if unlocked_only:
            query = query.filter(OwnedAspectModel.locked.is_(False))

        return [OwnedAspect.from_orm(a) for a in query.all()]


def get_aspect_by_id(aspect_id: int) -> Optional[OwnedAspect]:
    """Get an owned aspect by its ID (without image data)."""
    with get_session() as session:
        aspect = (
            session.query(OwnedAspectModel)
            .options(joinedload(OwnedAspectModel.aspect_definition))
            .filter(OwnedAspectModel.id == aspect_id)
            .first()
        )
        return OwnedAspect.from_orm(aspect) if aspect else None


def get_unique_aspect_names(chat_id: str, season_id: Optional[int] = None) -> List[str]:
    """Return the display names of all Unique aspects in a chat for the given season.

    Used to enforce name uniqueness when creating new Unique aspects.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session() as session:
        results = (
            session.query(OwnedAspectModel.name)
            .filter(
                OwnedAspectModel.chat_id == str(chat_id),
                OwnedAspectModel.rarity == "Unique",
                OwnedAspectModel.season_id == season_id,
            )
            .distinct()
            .all()
        )
        return [row[0] for row in results if row[0] is not None]


def get_aspect_with_image(aspect_id: int) -> Optional[OwnedAspectWithImage]:
    """Get an owned aspect by its ID, including image data."""
    with get_session() as session:
        aspect = (
            session.query(OwnedAspectModel)
            .options(
                joinedload(OwnedAspectModel.aspect_definition),
                joinedload(OwnedAspectModel.image),
            )
            .filter(OwnedAspectModel.id == aspect_id)
            .first()
        )
        return OwnedAspectWithImage.from_orm(aspect) if aspect else None


def get_aspect_image(aspect_id: int) -> Optional[str]:
    """Get the base64 encoded full-size image for an aspect.

    Only returns images for aspects in the current season.

    Args:
        aspect_id: The ID of the owned aspect.

    Returns:
        Base64 encoded image string, or None if not found or wrong season.
    """
    with get_session() as session:
        aspect = (
            session.query(OwnedAspectModel)
            .filter(
                OwnedAspectModel.id == aspect_id,
                OwnedAspectModel.season_id == CURRENT_SEASON,
            )
            .first()
        )
        if not aspect:
            return None

        aspect_image = (
            session.query(AspectImageModel).filter(AspectImageModel.aspect_id == aspect_id).first()
        )
        if not aspect_image or not aspect_image.image:
            return None
        return base64.b64encode(aspect_image.image).decode("utf-8")


def get_aspect_thumbnail(aspect_id: int) -> Optional[str]:
    """Get the thumbnail base64 image for an aspect, generating it if missing.

    Only returns images for aspects in the current season.
    Returns the 1/4-scale thumbnail (much smaller than the full image).

    Args:
        aspect_id: The ID of the owned aspect.

    Returns:
        Base64 encoded thumbnail string, or None if not found or wrong season.
    """
    with get_session(commit=True) as session:
        aspect = (
            session.query(OwnedAspectModel)
            .filter(
                OwnedAspectModel.id == aspect_id,
                OwnedAspectModel.season_id == CURRENT_SEASON,
            )
            .first()
        )
        if not aspect:
            return None

        aspect_image = (
            session.query(AspectImageModel).filter(AspectImageModel.aspect_id == aspect_id).first()
        )
        if not aspect_image:
            return None

        # Return cached thumbnail if available
        if aspect_image.thumbnail:
            return base64.b64encode(aspect_image.thumbnail).decode("utf-8")

        # Generate thumbnail from full image on-the-fly
        if not aspect_image.image:
            return None

        try:
            thumb_bytes = ImageUtil.compress_to_fraction(aspect_image.image, scale_factor=1 / 4)
            aspect_image.thumbnail = thumb_bytes
            return base64.b64encode(thumb_bytes).decode("utf-8")
        except Exception as exc:
            logger.warning("Failed to generate thumbnail for aspect %s: %s", aspect_id, exc)
            return base64.b64encode(aspect_image.image).decode("utf-8")


def get_aspect_images_batch(aspect_ids: List[int]) -> Dict[int, str]:
    """Get thumbnail base64 images for multiple aspects, generating them when missing.

    Only returns images for aspects in the current season.

    Args:
        aspect_ids: List of aspect IDs to fetch images for.

    Returns:
        Dictionary mapping aspect_id to thumbnail base64 string.
    """
    if not aspect_ids:
        return {}

    with get_session(commit=True) as session:
        # Filter to only aspects in the current season
        valid_ids = {
            row[0]
            for row in session.query(OwnedAspectModel.id)
            .filter(
                OwnedAspectModel.id.in_(aspect_ids),
                OwnedAspectModel.season_id == CURRENT_SEASON,
            )
            .all()
        }

        if not valid_ids:
            return {}

        aspect_images = (
            session.query(AspectImageModel).filter(AspectImageModel.aspect_id.in_(valid_ids)).all()
        )

        fetched: Dict[int, str] = {}
        for ai in aspect_images:
            aid = ai.aspect_id
            thumb = ai.thumbnail
            full = ai.image

            if thumb:
                fetched[aid] = base64.b64encode(thumb).decode("utf-8")
                continue

            if not full:
                continue

            try:
                thumb_bytes = ImageUtil.compress_to_fraction(full, scale_factor=1 / 4)
                ai.thumbnail = thumb_bytes
                fetched[aid] = base64.b64encode(thumb_bytes).decode("utf-8")
            except Exception as exc:
                logger.warning(
                    "Failed to generate thumbnail during batch fetch for aspect %s: %s",
                    aid,
                    exc,
                )
                fetched[aid] = base64.b64encode(full).decode("utf-8")

        return fetched


def get_aspects_for_card(card_id: int) -> List[CardAspect]:
    """Return the ordered list of aspects equipped on a card."""
    with get_session() as session:
        links = (
            session.query(CardAspectModel)
            .options(
                joinedload(CardAspectModel.aspect).joinedload(OwnedAspectModel.aspect_definition),
            )
            .filter(CardAspectModel.card_id == card_id)
            .order_by(CardAspectModel.order)
            .all()
        )
        return [CardAspect.from_orm(link) for link in links]


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


def add_owned_aspect(
    aspect_definition_id: Optional[int],
    chat_id: str,
    season_id: int,
    rarity: str,
    image: Optional[bytes],
    thumbnail: Optional[bytes],
    owner: Optional[str] = None,
    user_id: Optional[int] = None,
    name: Optional[str] = None,
) -> int:
    """Create a new owned aspect with its image record.

    ``owner`` and ``user_id`` are left ``None`` for rolled aspects pending
    claim.  ``name`` is used for Unique/custom aspects that have no catalog
    entry.

    Returns:
        The ID of the newly created ``OwnedAspectModel``.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    with get_session(commit=True) as session:
        aspect = OwnedAspectModel(
            aspect_definition_id=aspect_definition_id,
            name=name,
            owner=owner,
            user_id=user_id,
            chat_id=str(chat_id),
            season_id=season_id,
            rarity=rarity,
            locked=False,
            created_at=now,
        )
        session.add(aspect)
        session.flush()  # materialise ID

        if image or thumbnail:
            aspect_image = AspectImageModel(
                aspect_id=aspect.id,
                image=image,
                thumbnail=thumbnail,
                image_updated_at=now,
            )
            session.add(aspect_image)

        return aspect.id


def try_claim_aspect(
    aspect_id: int,
    user_id: int,
    username: str,
    chat_id: str,
) -> bool:
    """Atomically claim an aspect: row-lock, validate, deduct claim points,
    and assign ownership in a single transaction.

    Returns ``True`` on success, ``False`` if the aspect is already owned or
    the user has insufficient claim points.
    """
    with get_session(commit=True) as session:
        # Row-lock the aspect
        aspect = (
            session.query(OwnedAspectModel)
            .filter(
                OwnedAspectModel.id == aspect_id,
                OwnedAspectModel.season_id == CURRENT_SEASON,
            )
            .with_for_update()
            .first()
        )

        if aspect is None:
            return False

        # Already claimed
        if aspect.owner is not None or aspect.user_id is not None:
            return False

        # Determine claim cost
        cost = get_claim_cost(aspect.rarity)

        # Ensure claim row exists and check balance (same session)
        claim = (
            session.query(ClaimModel)
            .filter(
                ClaimModel.user_id == user_id,
                ClaimModel.chat_id == str(chat_id),
            )
            .with_for_update()
            .first()
        )

        if claim is None:
            claim = ClaimModel(user_id=user_id, chat_id=str(chat_id), balance=1)
            session.add(claim)
            session.flush()

        if claim.balance < cost:
            return False

        # Deduct and assign
        claim.balance -= cost
        aspect.owner = username
        aspect.user_id = user_id
        aspect.locked = False
        return True


def lock_aspect(aspect_id: int, user_id: int) -> Optional[bool]:
    """Toggle the lock on an owned aspect.

    Returns the new lock state, or ``None`` if the aspect was not found
    or is not owned by the user.
    """
    with get_session(commit=True) as session:
        aspect = (
            session.query(OwnedAspectModel)
            .filter(
                OwnedAspectModel.id == aspect_id,
                OwnedAspectModel.user_id == user_id,
            )
            .first()
        )
        if aspect is None:
            return None
        aspect.locked = not aspect.locked
        return aspect.locked


def set_aspect_owner(aspect_id: int, username: str, user_id: int) -> bool:
    """Assign an owner to an aspect (e.g. for slot wins).

    Returns ``True`` if the aspect was found and updated.
    """
    with get_session(commit=True) as session:
        aspect = session.query(OwnedAspectModel).filter(OwnedAspectModel.id == aspect_id).first()
        if not aspect:
            return False
        aspect.owner = username
        aspect.user_id = user_id
        return True


def update_aspect_file_id(aspect_id: int, file_id: str) -> bool:
    """Store the Telegram file_id for an aspect sphere image.

    Returns ``True`` if the aspect was found and updated.
    """
    with get_session(commit=True) as session:
        aspect = session.query(OwnedAspectModel).filter(OwnedAspectModel.id == aspect_id).first()
        if not aspect:
            return False
        aspect.file_id = file_id
        return True


def delete_aspect(aspect_id: int) -> bool:
    """Delete an owned aspect from the database (used during rerolls).

    Only works for unclaimed aspects in the current season.
    The cascade on OwnedAspectModel will also remove the related
    AspectImageModel row.
    """
    with get_session(commit=True) as session:
        deleted = (
            session.query(OwnedAspectModel)
            .filter(
                OwnedAspectModel.id == aspect_id,
                OwnedAspectModel.season_id == CURRENT_SEASON,
            )
            .delete()
        )
    logger.info("Deleted aspect %d: %s", aspect_id, deleted > 0)
    return deleted > 0


# ---------------------------------------------------------------------------
# Burn / Recycle
# ---------------------------------------------------------------------------


def burn_aspect(aspect_id: int, user_id: int, chat_id: str) -> Optional[int]:
    """Burn an owned, unequipped, unlocked aspect and award spins.

    Validates ownership, equipped-status, and lock before deleting.  Awards
    spins via the spin service (inline import to avoid circular deps).

    Returns the spin reward on success, or ``None`` on failure.
    """
    with get_session(commit=True) as session:
        aspect = (
            session.query(OwnedAspectModel)
            .outerjoin(CardAspectModel, CardAspectModel.aspect_id == OwnedAspectModel.id)
            .filter(
                OwnedAspectModel.id == aspect_id,
                OwnedAspectModel.user_id == user_id,
            )
            .first()
        )

        if aspect is None:
            return None

        # Must not be locked
        if aspect.locked:
            return None

        # Must not be equipped (check junction table)
        equipped = (
            session.query(CardAspectModel.id).filter(CardAspectModel.aspect_id == aspect_id).first()
        )
        if equipped is not None:
            return None

        reward = get_spin_reward(aspect.rarity)

        # Hard-delete aspect and its image (cascade handles AspectImageModel)
        session.delete(aspect)

    # Award spins outside the delete transaction (separate service call)
    if reward > 0:
        from utils.services.spin_service import increment_user_spins

        increment_user_spins(user_id, chat_id, reward)

    return reward


def recycle_aspects(
    aspect_ids: List[int],
    user_id: int,
) -> bool:
    """Validate and hard-delete a batch of aspects for recycling.

    All aspects must be:
    - Owned by ``user_id``
    - Unequipped (no ``card_aspects`` row)
    - Unlocked
    - The same rarity

    The caller is responsible for verifying the correct count and for
    generating the upgraded aspect afterwards.

    Returns ``True`` if all validations pass and deletion succeeds.
    """
    if not aspect_ids:
        return False

    with get_session(commit=True) as session:
        aspects = session.query(OwnedAspectModel).filter(OwnedAspectModel.id.in_(aspect_ids)).all()

        if len(aspects) != len(aspect_ids):
            return False

        # Validate ownership, lock, and rarity consistency
        expected_rarity = aspects[0].rarity
        for a in aspects:
            if a.user_id != user_id:
                return False
            if a.locked:
                return False
            if a.rarity != expected_rarity:
                return False

        # Validate none are equipped
        equipped_count = (
            session.query(CardAspectModel.id)
            .filter(CardAspectModel.aspect_id.in_(aspect_ids))
            .count()
        )
        if equipped_count > 0:
            return False

        # Hard-delete (cascade handles images)
        for a in aspects:
            session.delete(a)

    return True


# ---------------------------------------------------------------------------
# Equip
# ---------------------------------------------------------------------------


def _rarity_index(rarity: str) -> int:
    """Return the index of a rarity in RARITY_ORDER (lower = rarer)."""
    try:
        return RARITY_ORDER.index(rarity)
    except ValueError:
        return len(RARITY_ORDER)


def equip_aspect_on_card(
    aspect_id: int,
    card_id: int,
    user_id: int,
    name_prefix: str,
    chat_id: str,
) -> bool:
    """Equip an aspect onto a card.

    Validates:
    - Ownership match (both belong to ``user_id``)
    - Rarity compatibility (aspect rarity ≤ card rarity; Unique exempt)
    - ``aspect_count < 5``
    - Neither item is locked
    - Aspect is not already equipped

    On success, creates a ``CardAspectModel`` row, increments the card's
    ``aspect_count``, sets the card's ``modifier`` to ``name_prefix``, and
    emits an ``EQUIP`` event.

    Returns ``True`` on success, ``False`` on any validation failure.
    """
    from utils.services import event_service

    now = datetime.datetime.now(datetime.timezone.utc)

    with get_session(commit=True) as session:
        # Row-lock both objects
        card = (
            session.query(CardModel)
            .filter(
                CardModel.id == card_id,
                CardModel.season_id == CURRENT_SEASON,
            )
            .with_for_update()
            .first()
        )
        if card is None:
            return False

        aspect = (
            session.query(OwnedAspectModel)
            .filter(OwnedAspectModel.id == aspect_id)
            .with_for_update()
            .first()
        )
        if aspect is None:
            return False

        # Ownership checks
        if card.user_id != user_id or aspect.user_id != user_id:
            return False

        # Lock checks
        if card.locked or aspect.locked:
            return False

        # Capacity check
        if card.aspect_count >= 5:
            return False

        # Rarity compatibility (Unique aspects exempt)
        if aspect.rarity != "Unique":
            aspect_idx = _rarity_index(aspect.rarity)
            card_idx = _rarity_index(card.rarity)
            # Lower index = rarer. Aspect must be same or more common than card.
            if aspect_idx < card_idx:
                return False

        # Ensure aspect is not already equipped
        already_equipped = (
            session.query(CardAspectModel.id).filter(CardAspectModel.aspect_id == aspect_id).first()
        )
        if already_equipped is not None:
            return False

        # Create junction row
        new_order = card.aspect_count + 1
        link = CardAspectModel(
            card_id=card_id,
            aspect_id=aspect_id,
            order=new_order,
            equipped_at=now,
        )
        session.add(link)

        # Update card
        card.aspect_count = new_order
        card.modifier = name_prefix
        card.updated_at = now

    # Emit event outside the transaction
    event_service.log(
        EventType.EQUIP,
        EquipOutcome.SUCCESS,
        user_id=user_id,
        chat_id=chat_id,
        card_id=card_id,
        aspect_id=aspect_id,
        order=new_order,
        name_prefix=name_prefix,
    )

    return True
