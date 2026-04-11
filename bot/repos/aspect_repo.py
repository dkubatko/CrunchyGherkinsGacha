"""Aspect repository for database access to aspect definitions and owned aspects.

This module provides data access functions for creating, retrieving,
updating, and deleting aspect definitions and owned aspects.
"""

from __future__ import annotations

import base64
import datetime
import logging
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, noload

from settings.constants import CURRENT_SEASON
from utils.image import ImageUtil
from utils.models import (
    AspectDefinitionModel,
    AspectImageModel,
    CardAspectModel,
    CardModel,
    OwnedAspectModel,
    SetModel,
)
from utils.schemas import AspectDefinition, CardAspect, OwnedAspect, OwnedAspectWithImage
from utils.session import with_session

logger = logging.getLogger(__name__)

# Canonical rarity order for grouping output
_RARITY_ORDER = ("Common", "Rare", "Epic", "Legendary")


# ---------------------------------------------------------------------------
# Aspect definition queries
# ---------------------------------------------------------------------------


@with_session
def get_aspect_definitions_by_rarity(
    season_id: Optional[int] = None,
    source: Optional[str] = None,
    active_only: bool = True,
    *,
    session: Session,
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

    query = query.options(
        joinedload(AspectDefinitionModel.aspect_set),
    ).order_by(AspectDefinitionModel.name)
    rows = query.all()

    # Build grouped result
    grouped: Dict[str, List[AspectDefinitionModel]] = {}
    for ad in rows:
        grouped.setdefault(ad.rarity, []).append(ad)

    # Order by canonical rarity, then any extras alphabetically
    ordered: Dict[str, List[AspectDefinition]] = {}
    for rarity in _RARITY_ORDER:
        ordered[rarity] = [AspectDefinition.from_orm(m) for m in grouped.pop(rarity, [])]
    for rarity in sorted(grouped):
        ordered[rarity] = [AspectDefinition.from_orm(m) for m in grouped[rarity]]

    return ordered


@with_session
def get_aspect_definitions_by_set(
    set_id: int,
    season_id: Optional[int] = None,
    *,
    session: Session,
) -> List[AspectDefinition]:
    """Return all aspect definitions belonging to a set.

    Args:
        set_id: The set's ID within the season.
        season_id: Season to query. Defaults to ``CURRENT_SEASON``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    rows = (
        session.query(AspectDefinitionModel)
        .options(joinedload(AspectDefinitionModel.aspect_set))
        .filter(
            AspectDefinitionModel.set_id == set_id,
            AspectDefinitionModel.season_id == season_id,
        )
        .order_by(AspectDefinitionModel.rarity, AspectDefinitionModel.name)
        .all()
    )
    return [AspectDefinition.from_orm(m) for m in rows]


@with_session
def get_aspect_definition_by_id(
    definition_id: int,
    *,
    session: Session,
) -> Optional[AspectDefinition]:
    """Fetch a single aspect definition by its auto-increment ID."""
    row = (
        session.query(AspectDefinitionModel)
        .options(joinedload(AspectDefinitionModel.aspect_set))
        .filter(AspectDefinitionModel.id == definition_id)
        .first()
    )
    return AspectDefinition.from_orm(row) if row else None


@with_session
def get_aspect_definition_by_name_and_set(
    name: str,
    set_id: int,
    season_id: Optional[int] = None,
    *,
    session: Session,
) -> Optional[AspectDefinition]:
    """Lookup an aspect definition by name within a specific set.

    Args:
        name: The aspect keyword (case-sensitive).
        set_id: The set ID.
        season_id: Season to query. Defaults to ``CURRENT_SEASON``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    row = (
        session.query(AspectDefinitionModel)
        .options(joinedload(AspectDefinitionModel.aspect_set))
        .filter(
            AspectDefinitionModel.name == name,
            AspectDefinitionModel.set_id == set_id,
            AspectDefinitionModel.season_id == season_id,
        )
        .first()
    )
    return AspectDefinition.from_orm(row) if row else None


@with_session
def get_aspect_definition_count_per_set(
    season_id: Optional[int] = None,
    *,
    session: Session,
) -> Dict[int, int]:
    """Return a mapping of set_id → number of aspect definitions for the season."""
    if season_id is None:
        season_id = CURRENT_SEASON

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


@with_session
def get_owned_count_for_definition(definition_id: int, *, session: Session) -> int:
    """Return the number of owned aspect instances linked to a definition."""
    return (
        session.query(func.count(OwnedAspectModel.id))
        .filter(OwnedAspectModel.aspect_definition_id == definition_id)
        .scalar()
        or 0
    )


# ---------------------------------------------------------------------------
# Aspect definition CRUD
# ---------------------------------------------------------------------------


@with_session(commit=True)
def create_aspect_definition(
    set_id: int,
    name: str,
    rarity: str,
    season_id: Optional[int] = None,
    *,
    session: Session,
) -> AspectDefinition:
    """Create a new aspect definition in the database.

    Args:
        set_id: The set this definition belongs to.
        name: The aspect keyword.
        rarity: The rarity level (Common / Rare / Epic / Legendary).
        season_id: Season ID. Defaults to ``CURRENT_SEASON``.

    Returns:
        The newly created ``AspectDefinition``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    now = datetime.datetime.now(datetime.timezone.utc)

    definition = AspectDefinitionModel(
        set_id=set_id,
        season_id=season_id,
        name=name,
        rarity=rarity,
        created_at=now,
    )
    session.add(definition)
    session.flush()
    # Re-fetch with eager-loaded relationship for the DTO
    definition = (
        session.query(AspectDefinitionModel)
        .options(joinedload(AspectDefinitionModel.aspect_set))
        .filter(AspectDefinitionModel.id == definition.id)
        .one()
    )
    logger.info(
        "Created aspect definition id=%s name='%s' rarity=%s set=%s season=%s",
        definition.id,
        name,
        rarity,
        set_id,
        season_id,
    )
    return AspectDefinition.from_orm(definition)


@with_session(commit=True)
def update_aspect_definition(
    definition_id: int,
    *,
    name: Optional[str] = None,
    rarity: Optional[str] = None,
    set_id: Optional[int] = None,
    session: Session,
) -> Optional[AspectDefinition]:
    """Update an existing aspect definition's fields.

    Only provided (non-None) fields are updated.

    Returns:
        The updated ``AspectDefinition``, or ``None`` if not found.
    """
    definition = (
        session.query(AspectDefinitionModel)
        .options(joinedload(AspectDefinitionModel.aspect_set))
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
    return AspectDefinition.from_orm(definition)


@with_session(commit=True)
def delete_aspect_definition(definition_id: int, *, session: Session) -> tuple[bool, str]:
    """Delete an aspect definition if it is not linked to any owned aspects.

    Returns:
        A tuple ``(success: bool, message: str)``.
    """
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


@with_session(commit=True)
def bulk_upsert_aspect_definitions(
    definitions: list[dict],
    season_id: Optional[int] = None,
    *,
    session: Session,
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


@with_session
def get_user_aspects(
    user_id: int,
    season_id: Optional[int] = None,
    chat_id: Optional[str] = None,
    rarity: Optional[str] = None,
    unlocked_only: bool = False,
    *,
    session: Session,
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

    query = (
        session.query(OwnedAspectModel)
        .outerjoin(CardAspectModel, CardAspectModel.aspect_id == OwnedAspectModel.id)
        .filter(
            OwnedAspectModel.user_id == user_id,
            OwnedAspectModel.season_id == season_id,
            CardAspectModel.id.is_(None),  # unequipped only
        )
        .options(
            joinedload(OwnedAspectModel.aspect_definition).joinedload(
                AspectDefinitionModel.aspect_set
            ),
        )
    )
    if chat_id is not None:
        query = query.filter(OwnedAspectModel.chat_id == str(chat_id))
    if rarity is not None:
        query = query.filter(OwnedAspectModel.rarity == rarity)
    if unlocked_only:
        query = query.filter(OwnedAspectModel.locked.is_(False))

    return [OwnedAspect.from_orm(m) for m in query.all()]


@with_session
def get_aspect_by_id(aspect_id: int, *, session: Session) -> Optional[OwnedAspect]:
    """Get an owned aspect by its ID (without image data)."""
    row = (
        session.query(OwnedAspectModel)
        .options(
            joinedload(OwnedAspectModel.aspect_definition).joinedload(
                AspectDefinitionModel.aspect_set
            ),
        )
        .filter(OwnedAspectModel.id == aspect_id)
        .first()
    )
    return OwnedAspect.from_orm(row) if row else None


@with_session
def get_unique_aspect_names(
    chat_id: str, season_id: Optional[int] = None, *, session: Session
) -> List[str]:
    """Return the display names of all Unique aspects in a chat for the given season.

    Used to enforce name uniqueness when creating new Unique aspects.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

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


@with_session
def get_aspect_with_image(aspect_id: int, *, session: Session) -> Optional[OwnedAspectWithImage]:
    """Get an owned aspect by its ID, including image data."""
    row = (
        session.query(OwnedAspectModel)
        .options(
            joinedload(OwnedAspectModel.aspect_definition).joinedload(
                AspectDefinitionModel.aspect_set
            ),
            joinedload(OwnedAspectModel.image),
        )
        .filter(OwnedAspectModel.id == aspect_id)
        .first()
    )
    return OwnedAspectWithImage.from_orm(row) if row else None


@with_session
def get_aspect_image(aspect_id: int, *, session: Session) -> Optional[str]:
    """Get the base64 encoded full-size image for an aspect.

    Only returns images for aspects in the current season.

    Args:
        aspect_id: The ID of the owned aspect.

    Returns:
        Base64 encoded image string, or None if not found or wrong season.
    """
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


@with_session(commit=True)
def get_aspect_thumbnail(aspect_id: int, *, session: Session) -> Optional[str]:
    """Get the thumbnail base64 image for an aspect, generating it if missing.

    Only returns images for aspects in the current season.
    Returns the 1/4-scale thumbnail (much smaller than the full image).

    Args:
        aspect_id: The ID of the owned aspect.

    Returns:
        Base64 encoded thumbnail string, or None if not found or wrong season.
    """
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


@with_session(commit=True)
def get_aspect_images_batch(aspect_ids: List[int], *, session: Session) -> Dict[int, str]:
    """Get thumbnail base64 images for multiple aspects, generating them when missing.

    Only returns images for aspects in the current season.

    Args:
        aspect_ids: List of aspect IDs to fetch images for.

    Returns:
        Dictionary mapping aspect_id to thumbnail base64 string.
    """
    if not aspect_ids:
        return {}

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


@with_session
def get_aspects_for_card(card_id: int, *, session: Session) -> List[CardAspect]:
    """Return the ordered list of aspects equipped on a card."""
    rows = (
        session.query(CardAspectModel)
        .options(
            joinedload(CardAspectModel.aspect)
            .joinedload(OwnedAspectModel.aspect_definition)
            .joinedload(AspectDefinitionModel.aspect_set),
        )
        .filter(CardAspectModel.card_id == card_id)
        .order_by(CardAspectModel.order)
        .all()
    )
    return [CardAspect.from_orm(m) for m in rows]


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


@with_session(commit=True)
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
    *,
    session: Session,
) -> int:
    """Create a new owned aspect with its image record.

    ``owner`` and ``user_id`` are left ``None`` for rolled aspects pending
    claim.  ``name`` is used for Unique/custom aspects that have no catalog
    entry.

    Returns:
        The ID of the newly created ``OwnedAspectModel``.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
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


@with_session(commit=True)
def lock_aspect(aspect_id: int, user_id: int, *, session: Session) -> Optional[bool]:
    """Toggle the lock on an owned aspect.

    Returns the new lock state, or ``None`` if the aspect was not found
    or is not owned by the user.
    """
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


@with_session(commit=True)
def set_aspect_owner(
    aspect_id: int, username: str, user_id: int, *, locked: Optional[bool] = None, session: Session
) -> bool:
    """Assign an owner to an aspect (e.g. for slot wins).

    Returns ``True`` if the aspect was found and updated.
    """
    aspect = session.query(OwnedAspectModel).filter(OwnedAspectModel.id == aspect_id).first()
    if not aspect:
        return False
    aspect.owner = username
    aspect.user_id = user_id
    if locked is not None:
        aspect.locked = locked
    return True


@with_session(commit=True)
def update_aspect_file_id(aspect_id: int, file_id: str, *, session: Session) -> bool:
    """Store the Telegram file_id for an aspect sphere image.

    Returns ``True`` if the aspect was found and updated.
    """
    aspect = session.query(OwnedAspectModel).filter(OwnedAspectModel.id == aspect_id).first()
    if not aspect:
        return False
    aspect.file_id = file_id
    return True


@with_session(commit=True)
def delete_aspect(aspect_id: int, *, session: Session) -> bool:
    """Delete an owned aspect from the database (used during rerolls).

    Only works for unclaimed aspects in the current season.
    The cascade on OwnedAspectModel will also remove the related
    AspectImageModel row.
    """
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


@with_session(commit=True)
def transfer_equipped_aspect_ownership(
    card_id: int, owner: str, user_id: int, *, session: Session
) -> None:
    """Set ``owner``/``user_id`` on every aspect equipped on a card.

    Expects an existing session (caller manages the transaction).
    """
    equipped_aspect_ids = (
        session.query(CardAspectModel.aspect_id).filter(CardAspectModel.card_id == card_id).all()
    )
    if not equipped_aspect_ids:
        return

    ids = [row[0] for row in equipped_aspect_ids]
    session.query(OwnedAspectModel).filter(OwnedAspectModel.id.in_(ids)).update(
        {
            OwnedAspectModel.owner: owner,
            OwnedAspectModel.user_id: user_id,
        },
        synchronize_session="fetch",
    )


@with_session
def get_unowned_aspect_for_update(aspect_id: int, *, session: Session) -> Optional[OwnedAspect]:
    """Get an unclaimed current-season aspect with row lock."""
    row = (
        session.query(OwnedAspectModel)
        .options(noload("*"))
        .filter(
            OwnedAspectModel.id == aspect_id,
            OwnedAspectModel.season_id == CURRENT_SEASON,
        )
        .with_for_update()
        .first()
    )
    return OwnedAspect.from_orm(row) if row else None


@with_session
def get_aspect_for_update(aspect_id: int, *, session: Session) -> Optional[OwnedAspect]:
    """Get an aspect with row lock."""
    row = (
        session.query(OwnedAspectModel)
        .options(noload("*"))
        .filter(OwnedAspectModel.id == aspect_id)
        .with_for_update()
        .first()
    )
    return OwnedAspect.from_orm(row) if row else None


@with_session
def get_owned_aspect(aspect_id: int, user_id: int, *, session: Session) -> Optional[OwnedAspect]:
    """Get an aspect owned by a specific user."""
    row = (
        session.query(OwnedAspectModel)
        .options(
            joinedload(OwnedAspectModel.aspect_definition).joinedload(
                AspectDefinitionModel.aspect_set
            ),
        )
        .filter(
            OwnedAspectModel.id == aspect_id,
            OwnedAspectModel.user_id == user_id,
        )
        .first()
    )
    return OwnedAspect.from_orm(row) if row else None


@with_session
def is_aspect_equipped(aspect_id: int, *, session: Session) -> bool:
    """Check if an aspect is equipped on any card."""
    return (
        session.query(CardAspectModel.id).filter(CardAspectModel.aspect_id == aspect_id).first()
    ) is not None


@with_session(commit=True)
def swap_aspect_owners(aspect_id1: int, aspect_id2: int, *, session: Session) -> bool:
    """Swap the owners of two aspects."""
    aspect1 = session.query(OwnedAspectModel).filter(OwnedAspectModel.id == aspect_id1).first()
    if not aspect1:
        return False
    aspect2 = session.query(OwnedAspectModel).filter(OwnedAspectModel.id == aspect_id2).first()
    if not aspect2:
        return False

    aspect1.owner, aspect2.owner = aspect2.owner, aspect1.owner
    aspect1.user_id, aspect2.user_id = aspect2.user_id, aspect1.user_id
    return True


@with_session
def get_aspects_by_ids(aspect_ids: List[int], *, session: Session) -> List[OwnedAspect]:
    """Get multiple aspects by their IDs."""
    rows = (
        session.query(OwnedAspectModel)
        .options(
            joinedload(OwnedAspectModel.aspect_definition).joinedload(
                AspectDefinitionModel.aspect_set
            ),
        )
        .filter(OwnedAspectModel.id.in_(aspect_ids))
        .all()
    )
    return [OwnedAspect.from_orm(m) for m in rows]


@with_session
def count_equipped_in_ids(aspect_ids: List[int], *, session: Session) -> int:
    """Count how many of the given aspects are equipped."""
    return (
        session.query(CardAspectModel.id).filter(CardAspectModel.aspect_id.in_(aspect_ids)).count()
    )


@with_session(commit=True)
def create_card_aspect_link(
    card_id: int,
    aspect_id: int,
    order: int,
    equipped_at: datetime.datetime,
    *,
    session: Session,
) -> CardAspect:
    """Create a junction record linking an aspect to a card."""
    link = CardAspectModel(
        card_id=card_id,
        aspect_id=aspect_id,
        order=order,
        equipped_at=equipped_at,
    )
    session.add(link)
    session.flush()
    # Re-fetch with eager-loaded relationships for the DTO
    link = (
        session.query(CardAspectModel)
        .options(
            joinedload(CardAspectModel.aspect)
            .joinedload(OwnedAspectModel.aspect_definition)
            .joinedload(AspectDefinitionModel.aspect_set),
        )
        .filter(CardAspectModel.id == link.id)
        .one()
    )
    return CardAspect.from_orm(link)


@with_session(commit=True)
def delete_aspect_by_id(aspect_id: int, *, session: Session) -> bool:
    """Delete an owned aspect by ID (cascade handles related records)."""
    aspect = session.query(OwnedAspectModel).filter(OwnedAspectModel.id == aspect_id).first()
    if not aspect:
        return False
    session.delete(aspect)
    return True


@with_session
def get_chat_aspects_for_trade(
    chat_id: str,
    exclude_user_id: int,
    season_id: Optional[int] = None,
    *,
    session: Session,
) -> List[OwnedAspect]:
    """Return all tradeable aspects in a chat, excluding those owned by a specific user.

    Only returns aspects that are unequipped, making them eligible for trading.
    Used to populate trade options in the mini app.

    Args:
        chat_id: The chat to scope the query to.
        exclude_user_id: User ID to exclude (the trade initiator).
        season_id: Season filter (defaults to ``CURRENT_SEASON``).
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    rows = (
        session.query(OwnedAspectModel)
        .outerjoin(CardAspectModel, CardAspectModel.aspect_id == OwnedAspectModel.id)
        .filter(
            OwnedAspectModel.chat_id == str(chat_id),
            OwnedAspectModel.season_id == season_id,
            OwnedAspectModel.user_id != exclude_user_id,
            OwnedAspectModel.user_id.isnot(None),
            CardAspectModel.id.is_(None),  # unequipped only
        )
        .options(
            joinedload(OwnedAspectModel.aspect_definition).joinedload(
                AspectDefinitionModel.aspect_set
            ),
        )
        .all()
    )
    return [OwnedAspect.from_orm(row) for row in rows]


@with_session
def get_all_chat_aspects(
    chat_id: str,
    season_id: Optional[int] = None,
    *,
    session: Session,
) -> List[OwnedAspect]:
    """Return all unequipped aspects in a chat across all users.

    Used to populate the read-only "All > Aspects" view in the mini app.

    Args:
        chat_id: The chat to scope the query to.
        season_id: Season filter (defaults to ``CURRENT_SEASON``).
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    rows = (
        session.query(OwnedAspectModel)
        .outerjoin(CardAspectModel, CardAspectModel.aspect_id == OwnedAspectModel.id)
        .filter(
            OwnedAspectModel.chat_id == str(chat_id),
            OwnedAspectModel.season_id == season_id,
            OwnedAspectModel.user_id.isnot(None),
            CardAspectModel.id.is_(None),  # unequipped only
        )
        .options(
            joinedload(OwnedAspectModel.aspect_definition).joinedload(
                AspectDefinitionModel.aspect_set
            ),
        )
        .all()
    )
    return [OwnedAspect.from_orm(row) for row in rows]
    """Swap the owners of two aspects atomically."""
    aspect1 = session.query(OwnedAspectModel).filter(OwnedAspectModel.id == aspect_id1).first()
    aspect2 = session.query(OwnedAspectModel).filter(OwnedAspectModel.id == aspect_id2).first()
    if not aspect1 or not aspect2:
        return False
    aspect1.owner, aspect2.owner = aspect2.owner, aspect1.owner
    aspect1.user_id, aspect2.user_id = aspect2.user_id, aspect1.user_id
    return True
