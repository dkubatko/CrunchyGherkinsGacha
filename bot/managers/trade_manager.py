"""Trade manager — trade logic.

All trade mutations — card-for-card and aspect-for-aspect — are routed
through this manager so that equipped-aspect ownership never diverges
from card ownership.
"""

from __future__ import annotations

import logging
from typing import Optional

from repos import aspect_repo, card_repo
from utils.session import get_session

logger = logging.getLogger(__name__)


def trade_cards(card_id1: int, card_id2: int) -> Optional[str]:
    """Atomically swap ownership of two cards **and** all their equipped aspects.

    For each card, every ``OwnedAspectModel`` linked through ``card_aspects``
    has its ``owner`` / ``user_id`` updated to match the new card owner.

    Only works for cards in the current season.

    Returns ``None`` on success, or a human-readable error string on failure.
    """
    try:
        with get_session(commit=True) as session:
            card1 = card_repo.get_card_for_update(card_id1, session=session)
            if not card1:
                return "One of the cards no longer exists."

            card2 = card_repo.get_card_for_update(card_id2, session=session)
            if not card2:
                return "One of the cards no longer exists."

            # Swap card ownership
            card_repo.swap_card_owners(card_id1, card_id2, session=session)

            # Transfer equipped-aspect ownership to match new card owners
            # After swap: card1 is now owned by card2's original owner and vice versa
            aspect_repo.transfer_equipped_aspect_ownership(card_id1, card2.owner, card2.user_id, session=session)
            aspect_repo.transfer_equipped_aspect_ownership(card_id2, card1.owner, card1.user_id, session=session)

            return None
    except Exception:
        logger.exception("trade_cards failed for card_ids %s, %s", card_id1, card_id2)
        return "Trade failed due to an internal error."


def trade_aspects(aspect_id1: int, aspect_id2: int) -> Optional[str]:
    """Atomically swap ownership of two unequipped aspects.

    Returns ``None`` on success, or a human-readable error string on failure.
    """
    try:
        with get_session(commit=True) as session:
            aspect1 = aspect_repo.get_aspect_for_update(aspect_id1, session=session)
            if not aspect1:
                return "One of the aspects no longer exists."

            aspect2 = aspect_repo.get_aspect_for_update(aspect_id2, session=session)
            if not aspect2:
                return "One of the aspects no longer exists."

            # Neither may be equipped
            if aspect_repo.is_aspect_equipped(aspect_id1, session=session):
                return "Your aspect is equipped on a card and must be unequipped before trading."
            if aspect_repo.is_aspect_equipped(aspect_id2, session=session):
                return "The other aspect is equipped on a card and must be unequipped before trading."

            # Swap ownership
            aspect_repo.swap_aspect_owners(aspect_id1, aspect_id2, session=session)

            return None
    except Exception:
        logger.exception("trade_aspects failed for aspect_ids %s, %s", aspect_id1, aspect_id2)
        return "Trade failed due to an internal error."
