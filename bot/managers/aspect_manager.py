"""Aspect manager — aspect business logic.

Handles claiming, burning, recycling, and equipping aspects with
validation, row-locking, and cross-model orchestration.
"""

from __future__ import annotations

import datetime
import logging
from typing import List, Optional

from settings.constants import RARITY_ORDER, get_claim_cost, get_spin_reward
from utils.events import EquipOutcome, EventType
from repos import aspect_repo, card_repo, claim_repo
from utils.session import get_session

logger = logging.getLogger(__name__)


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
        aspect = aspect_repo.get_unowned_aspect_for_update(aspect_id, session=session)

        if aspect is None:
            return False

        # Already claimed
        if aspect.owner is not None or aspect.user_id is not None:
            return False

        cost = get_claim_cost(aspect.rarity)

        claim = claim_repo.get_or_create_claim_for_update(user_id, chat_id, session=session)

        if claim.balance < cost:
            return False

        # Deduct and assign
        claim_repo.reduce_claim_points(user_id, chat_id, cost, session=session)
        aspect_repo.set_aspect_owner(aspect_id, username, user_id, locked=False, session=session)
        return True


def burn_aspect(aspect_id: int, user_id: int, chat_id: str) -> Optional[int]:
    """Burn an owned, unequipped, unlocked aspect and award spins.

    Validates ownership, equipped-status, and lock before deleting.  Awards
    spins via the spin service (inline import to avoid circular deps).

    Returns the spin reward on success, or ``None`` on failure.
    """
    with get_session(commit=True) as session:
        aspect = aspect_repo.get_owned_aspect(aspect_id, user_id, session=session)

        if aspect is None:
            return None

        if aspect.locked:
            return None

        if aspect_repo.is_aspect_equipped(aspect_id, session=session):
            return None

        reward = get_spin_reward(aspect.rarity)

        aspect_repo.delete_aspect_by_id(aspect_id, session=session)

    # Award spins outside the delete transaction (separate service call)
    if reward > 0:
        from repos import spin_repo

        spin_repo.increment_user_spins(user_id, chat_id, reward)

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
        aspects = aspect_repo.get_aspects_by_ids(aspect_ids, session=session)

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
        equipped_count = aspect_repo.count_equipped_in_ids(aspect_ids, session=session)
        if equipped_count > 0:
            return False

        # Hard-delete (cascade handles images)
        for a in aspects:
            aspect_repo.delete_aspect_by_id(a.id, session=session)

    return True


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
    from managers import event_manager as event_service

    now = datetime.datetime.now(datetime.timezone.utc)

    with get_session(commit=True) as session:
        card = card_repo.get_card_for_update(card_id, session=session)
        if card is None:
            return False

        aspect = aspect_repo.get_aspect_for_update(aspect_id, session=session)
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
        if aspect_repo.is_aspect_equipped(aspect_id, session=session):
            return False

        # Create junction row
        new_order = card.aspect_count + 1
        aspect_repo.create_card_aspect_link(card_id, aspect_id, new_order, now, session=session)

        # Update card
        card_repo.update_card_aspect_equip(card_id, aspect_count=new_order, modifier=name_prefix, updated_at=now, session=session)

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
