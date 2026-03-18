"""Trade service for atomic card and aspect trades.

All trade mutations — card-for-card and aspect-for-aspect — are routed
through this service so that equipped-aspect ownership never diverges
from card ownership.
"""

from __future__ import annotations

import logging
from typing import Optional

from settings.constants import CURRENT_SEASON
from utils.models import CardAspectModel, CardModel, OwnedAspectModel
from utils.session import get_session

logger = logging.getLogger(__name__)


def trade_cards(card_id1: int, card_id2: int) -> bool:
    """Atomically swap ownership of two cards **and** all their equipped aspects.

    For each card, every ``OwnedAspectModel`` linked through ``card_aspects``
    has its ``owner`` / ``user_id`` updated to match the new card owner.

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
                .with_for_update()
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
                .with_for_update()
                .first()
            )
            if not card2:
                return False

            # Swap card ownership
            card1.owner, card2.owner = card2.owner, card1.owner
            card1.user_id, card2.user_id = card2.user_id, card1.user_id

            # Transfer equipped-aspect ownership to match new card owners
            _transfer_equipped_aspect_ownership(session, card1)
            _transfer_equipped_aspect_ownership(session, card2)

            return True
    except Exception:
        logger.exception("trade_cards failed for card_ids %s, %s", card_id1, card_id2)
        return False


def trade_aspects(aspect_id1: int, aspect_id2: int) -> bool:
    """Atomically swap ownership of two unequipped, unlocked aspects.

    Returns ``False`` if either aspect is not found, is equipped, or is
    locked.
    """
    try:
        with get_session(commit=True) as session:
            aspect1 = (
                session.query(OwnedAspectModel)
                .filter(OwnedAspectModel.id == aspect_id1)
                .with_for_update()
                .first()
            )
            if not aspect1:
                return False

            aspect2 = (
                session.query(OwnedAspectModel)
                .filter(OwnedAspectModel.id == aspect_id2)
                .with_for_update()
                .first()
            )
            if not aspect2:
                return False

            # Both must be unlocked
            if aspect1.locked or aspect2.locked:
                return False

            # Neither may be equipped
            eq1 = (
                session.query(CardAspectModel.id)
                .filter(CardAspectModel.aspect_id == aspect_id1)
                .first()
            )
            eq2 = (
                session.query(CardAspectModel.id)
                .filter(CardAspectModel.aspect_id == aspect_id2)
                .first()
            )
            if eq1 is not None or eq2 is not None:
                return False

            # Swap ownership
            aspect1.owner, aspect2.owner = aspect2.owner, aspect1.owner
            aspect1.user_id, aspect2.user_id = aspect2.user_id, aspect1.user_id

            return True
    except Exception:
        logger.exception("trade_aspects failed for aspect_ids %s, %s", aspect_id1, aspect_id2)
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _transfer_equipped_aspect_ownership(session, card: CardModel) -> None:
    """Set ``owner``/``user_id`` on every aspect equipped on *card* to match
    the card's current owner values.
    """
    equipped_aspect_ids = (
        session.query(CardAspectModel.aspect_id).filter(CardAspectModel.card_id == card.id).all()
    )
    if not equipped_aspect_ids:
        return

    ids = [row[0] for row in equipped_aspect_ids]
    session.query(OwnedAspectModel).filter(OwnedAspectModel.id.in_(ids)).update(
        {
            OwnedAspectModel.owner: card.owner,
            OwnedAspectModel.user_id: card.user_id,
        },
        synchronize_session="fetch",
    )
