"""Card manager — card claiming and recycling logic.

Handles atomic card claiming with row-locking, claim point deduction,
and ownership assignment.  Also handles card recycling (batch deletion).
"""

from __future__ import annotations

import datetime
from typing import List, Optional

from repos import card_repo, claim_repo
from utils.session import get_session


def try_claim_card(
    card_id: int,
    owner: str,
    user_id: Optional[int] = None,
    chat_id: Optional[str] = None,
    claim_cost: Optional[int] = None,
) -> bool:
    """Atomically claim a card: row-lock, validate, deduct claim points,
    and assign ownership in a single transaction.

    When ``chat_id`` and ``claim_cost`` are provided the claim-point
    deduction happens inside the same transaction (no race window).
    If they are omitted the function behaves like a simple ownership
    assignment (backward-compatible with callers that handle balance
    externally).

    Only works for cards in the current season.
    """
    with get_session(commit=True) as session:
        card = card_repo.get_unclaimed_card_for_update(card_id, session=session)

        if card is None:
            return False

        # If claim cost info provided, deduct in same transaction
        if (
            chat_id is not None
            and claim_cost is not None
            and claim_cost > 0
            and user_id is not None
        ):
            claim = claim_repo.get_or_create_claim_for_update(user_id, chat_id, session=session)

            if claim.balance < claim_cost:
                return False

            claim_repo.reduce_claim_points(user_id, chat_id, claim_cost, session=session)

        now = datetime.datetime.now(datetime.timezone.utc)
        card_repo.set_card_owner(card_id, owner, user_id, updated_at=now, session=session)
        return True


def recycle_cards(card_ids: List[int], user_id: int) -> bool:
    """Validate and hard-delete cards for recycling.

    All cards must be owned by ``user_id``, unlocked, and the same rarity.
    Equipped aspects are destroyed with the cards (cascade).

    Returns ``True`` if all validations pass and deletion succeeds.
    """
    if not card_ids:
        return False

    with get_session(commit=True) as session:
        cards = []
        for cid in card_ids:
            card = card_repo.get_card(cid, session=session)
            if not card:
                return False
            cards.append(card)

        expected_rarity = cards[0].rarity
        for c in cards:
            if c.user_id != user_id:
                return False
            if c.locked:
                return False
            if c.rarity != expected_rarity:
                return False

        deleted = card_repo.delete_cards(card_ids, session=session)
        return deleted == len(card_ids)
