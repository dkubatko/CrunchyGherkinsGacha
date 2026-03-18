"""Aspect service for managing owned aspects.

This module provides all aspect-related business logic including
creating, retrieving, claiming, locking, burning, recycling, and
equipping aspects onto cards.
"""

from __future__ import annotations

import datetime
import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import joinedload

from settings.constants import CURRENT_SEASON, RARITY_ORDER, get_claim_cost, get_spin_reward
from utils.events import EquipOutcome, EventType
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


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


def get_user_aspects(
    user_id: int,
    season_id: Optional[int] = None,
    chat_id: Optional[str] = None,
) -> List[OwnedAspect]:
    """Get all unequipped aspects owned by a user for the given season.

    "Unequipped" means the aspect has no entry in ``card_aspects``.
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
