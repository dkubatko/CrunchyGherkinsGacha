"""Trade manager — polymorphic trade logic.

Supports card↔card, aspect↔aspect, and cross-type (card↔aspect) trades.
All trade mutations are routed through ``execute_trade`` so that
equipped-aspect ownership never diverges from card ownership.
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from repos import aspect_repo, card_repo
from utils.session import get_session

logger = logging.getLogger(__name__)

TradeItemType = Literal["card", "aspect"]
VALID_TRADE_TYPES: set[str] = {"card", "aspect"}


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------

def execute_trade(
    offer_type: TradeItemType,
    offer_id: int,
    want_type: TradeItemType,
    want_id: int,
) -> Optional[str]:
    """Execute a trade between any two items.

    Returns ``None`` on success, or a human-readable error string.
    """
    if offer_type == "card" and want_type == "card":
        return trade_cards(offer_id, want_id)
    if offer_type == "aspect" and want_type == "aspect":
        return trade_aspects(offer_id, want_id)
    # Cross-type: normalise so we always call trade_card_for_aspect
    if offer_type == "card" and want_type == "aspect":
        return trade_card_for_aspect(offer_id, want_id)
    # aspect offered for card wanted
    return trade_card_for_aspect(want_id, offer_id)


# ---------------------------------------------------------------------------
# Same-type trades
# ---------------------------------------------------------------------------

def trade_cards(card_id1: int, card_id2: int) -> Optional[str]:
    """Atomically swap ownership of two cards **and** all their equipped aspects."""
    try:
        with get_session(commit=True) as session:
            card1 = card_repo.get_card_for_update(card_id1, session=session)
            if not card1:
                return "One of the cards no longer exists."

            card2 = card_repo.get_card_for_update(card_id2, session=session)
            if not card2:
                return "One of the cards no longer exists."

            card_repo.swap_card_owners(card_id1, card_id2, session=session)

            aspect_repo.transfer_equipped_aspect_ownership(card_id1, card2.owner, card2.user_id, session=session)
            aspect_repo.transfer_equipped_aspect_ownership(card_id2, card1.owner, card1.user_id, session=session)

            return None
    except Exception:
        logger.exception("trade_cards failed for card_ids %s, %s", card_id1, card_id2)
        return "Trade failed due to an internal error."


def trade_aspects(aspect_id1: int, aspect_id2: int) -> Optional[str]:
    """Atomically swap ownership of two unequipped aspects."""
    try:
        with get_session(commit=True) as session:
            aspect1 = aspect_repo.get_aspect_for_update(aspect_id1, session=session)
            if not aspect1:
                return "One of the aspects no longer exists."

            aspect2 = aspect_repo.get_aspect_for_update(aspect_id2, session=session)
            if not aspect2:
                return "One of the aspects no longer exists."

            if aspect_repo.is_aspect_equipped(aspect_id1, session=session):
                return "Your aspect is equipped on a card and must be unequipped before trading."
            if aspect_repo.is_aspect_equipped(aspect_id2, session=session):
                return "The other aspect is equipped on a card and must be unequipped before trading."

            aspect_repo.swap_aspect_owners(aspect_id1, aspect_id2, session=session)

            return None
    except Exception:
        logger.exception("trade_aspects failed for aspect_ids %s, %s", aspect_id1, aspect_id2)
        return "Trade failed due to an internal error."


# ---------------------------------------------------------------------------
# Cross-type trade
# ---------------------------------------------------------------------------

def trade_card_for_aspect(card_id: int, aspect_id: int) -> Optional[str]:
    """Transfer a card (with equipped aspects) for an aspect.

    The card + its equipped aspects go to the aspect owner.
    The aspect goes to the card owner.
    """
    try:
        with get_session(commit=True) as session:
            card = card_repo.get_card_for_update(card_id, session=session)
            if not card:
                return "The card no longer exists."

            aspect = aspect_repo.get_aspect_for_update(aspect_id, session=session)
            if not aspect:
                return "The aspect no longer exists."

            if aspect_repo.is_aspect_equipped(aspect_id, session=session):
                return "The aspect is equipped on a card and must be unequipped before trading."

            if card.chat_id != aspect.chat_id:
                return "The card and aspect must belong to the same chat."

            # Remember original owners before transfer
            card_owner, card_user_id = card.owner, card.user_id
            aspect_owner, aspect_user_id = aspect.owner, aspect.user_id

            if card_owner == aspect_owner:
                return "You cannot trade with yourself."

            # Transfer card + equipped aspects → aspect owner
            card_repo.transfer_card_ownership(card_id, aspect_owner, aspect_user_id, session=session)
            aspect_repo.transfer_equipped_aspect_ownership(card_id, aspect_owner, aspect_user_id, session=session)

            # Transfer aspect → card owner
            aspect_repo.transfer_aspect_ownership(aspect_id, card_owner, card_user_id, session=session)

            return None
    except Exception:
        logger.exception("trade_card_for_aspect failed for card %s, aspect %s", card_id, aspect_id)
        return "Trade failed due to an internal error."
