"""Ride the Bus (RTB) service for managing game state and logic.

Game Rules:
- 5 random cards from the chat are selected
- User wagers 10-50 spins
- First card is revealed, user guesses if next is higher/lower/equal (by rarity)
- Multipliers progress: x1 -> x2 -> x3 -> x5 -> x10
- Win: correctly guess all 4 comparisons
- Lose: incorrect guess loses the bet
- Cash out: take current winnings at any point after first correct guess
"""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timezone
from typing import Optional, Tuple

from utils.models import RideTheBusGameModel
from utils.schemas import RideTheBusGame
from utils.session import get_session
from utils.services import card_service
from settings.constants import (
    RARITY_ORDER,
    RTB_MIN_BET,
    RTB_MAX_BET,
    RTB_CARDS_PER_GAME,
    RTB_NUM_CARDS_TO_UNLOCK,
    RTB_MULTIPLIER_PROGRESSION,
)

logger = logging.getLogger(__name__)


def get_active_game(user_id: int, chat_id: str) -> Optional[RideTheBusGame]:
    """Get an active RTB game for a user in a chat."""
    with get_session() as session:
        game_orm = (
            session.query(RideTheBusGameModel)
            .filter(
                RideTheBusGameModel.user_id == user_id,
                RideTheBusGameModel.chat_id == chat_id,
                RideTheBusGameModel.status == "active",
            )
            .order_by(RideTheBusGameModel.started_timestamp.desc())
            .first()
        )
        return RideTheBusGame.from_orm(game_orm) if game_orm else None


def get_game_by_id(game_id: int) -> Optional[RideTheBusGame]:
    """Get an RTB game by ID."""
    with get_session() as session:
        game_orm = (
            session.query(RideTheBusGameModel).filter(RideTheBusGameModel.id == game_id).first()
        )
        return RideTheBusGame.from_orm(game_orm) if game_orm else None


def _select_random_cards(cards: list, count: int) -> list:
    """Select random cards for the game."""
    if len(cards) < count:
        return []
    return random.sample(cards, count)


def check_availability(chat_id: str) -> Tuple[bool, Optional[str]]:
    """Check if RTB game is available for a chat.

    Returns (is_available, reason_if_unavailable).
    Requires at least RTB_NUM_CARDS_TO_UNLOCK cards total and at least 1 card of each rarity.
    """
    all_cards = card_service.get_all_cards(chat_id=chat_id)
    total_cards = len(all_cards)

    if total_cards < RTB_NUM_CARDS_TO_UNLOCK:
        return False, f"Requires {RTB_NUM_CARDS_TO_UNLOCK - total_cards} more cards"

    # Check that we have at least 1 card of each rarity
    rarities_present = set(c.rarity for c in all_cards)
    missing_rarities = set(RARITY_ORDER) - rarities_present
    if missing_rarities:
        missing_list = ", ".join(sorted(missing_rarities))
        return False, f"Missing rarities: {missing_list}"

    return True, None


def create_game(
    user_id: int, chat_id: str, bet_amount: int
) -> Tuple[Optional[RideTheBusGame], Optional[str]]:
    """Create a new RTB game. Returns (game, error_message)."""
    if not (RTB_MIN_BET <= bet_amount <= RTB_MAX_BET):
        return None, f"Bet must be between {RTB_MIN_BET} and {RTB_MAX_BET} spins"

    if get_active_game(user_id, chat_id):
        return None, "You already have an active game. Finish it first!"

    # Select random cards from chat
    all_cards = card_service.get_all_cards(chat_id=chat_id)
    if len(all_cards) < RTB_CARDS_PER_GAME:
        return None, f"Not enough cards in this chat. Need at least {RTB_CARDS_PER_GAME} cards."

    selected = _select_random_cards(all_cards, RTB_CARDS_PER_GAME)
    if len(selected) < RTB_CARDS_PER_GAME:
        return None, "Could not select enough cards for the game."

    now = datetime.now(timezone.utc)

    with get_session(commit=True) as session:
        game_orm = RideTheBusGameModel(
            user_id=user_id,
            chat_id=chat_id,
            bet_amount=bet_amount,
            card_ids=json.dumps([c.id for c in selected]),
            card_rarities=json.dumps([c.rarity for c in selected]),
            card_titles=json.dumps([c.title() for c in selected]),
            current_position=1,
            current_multiplier=1,
            status="active",
            started_timestamp=now,
            last_updated_timestamp=now,
        )
        session.add(game_orm)
        session.flush()

        logger.info(f"Created RTB game {game_orm.id} for user {user_id} with bet {bet_amount}")
        return RideTheBusGame.from_orm(game_orm), None


def process_guess(game_id: int, guess: str) -> Tuple[Optional[RideTheBusGame], bool, Optional[str]]:
    """Process a guess. Returns (updated_game, was_correct, error_message)."""
    guess = guess.lower().strip()
    if guess not in ("higher", "lower", "equal"):
        return None, False, "Invalid guess. Must be 'higher', 'lower', or 'equal'"

    game = get_game_by_id(game_id)
    if not game:
        return None, False, "Game not found"
    if game.status != "active":
        return None, False, f"Game is not active (status: {game.status})"
    if game.current_position >= RTB_CARDS_PER_GAME:
        return None, False, "Game is already complete"

    # Compare current and next card rarities
    current_rarity = game.card_rarities[game.current_position - 1]
    next_rarity = game.card_rarities[game.current_position]

    try:
        diff = RARITY_ORDER.index(next_rarity) - RARITY_ORDER.index(current_rarity)
    except ValueError:
        diff = 0

    if diff > 0:
        actual = "higher"
    elif diff < 0:
        actual = "lower"
    else:
        actual = "equal"
    correct = guess == actual
    now = datetime.now(timezone.utc)

    with get_session(commit=True) as session:
        game_orm = (
            session.query(RideTheBusGameModel).filter(RideTheBusGameModel.id == game_id).first()
        )
        if not game_orm:
            return None, False, "Game not found"

        if correct:
            game_orm.current_position += 1
            game_orm.current_multiplier = RTB_MULTIPLIER_PROGRESSION.get(
                game_orm.current_position, game_orm.current_multiplier
            )
            game_orm.status = "won" if game_orm.current_position >= RTB_CARDS_PER_GAME else "active"
        else:
            game_orm.status = "lost"

        game_orm.last_updated_timestamp = now
        session.flush()

        logger.info(
            f"RTB game {game_id}: guess={guess}, actual={actual}, correct={correct}, status={game_orm.status}"
        )
        return RideTheBusGame.from_orm(game_orm), correct, None


def cash_out(game_id: int) -> Tuple[Optional[RideTheBusGame], int, Optional[str]]:
    """Cash out of an RTB game. Returns (updated_game, payout, error_message)."""
    game = get_game_by_id(game_id)
    if not game:
        return None, 0, "Game not found"
    if game.status != "active":
        return None, 0, f"Game is not active (status: {game.status})"
    if game.current_position < 2:
        return None, 0, "Cannot cash out before making at least one correct guess"

    payout = game.bet_amount * game.current_multiplier
    now = datetime.now(timezone.utc)

    with get_session(commit=True) as session:
        game_orm = (
            session.query(RideTheBusGameModel).filter(RideTheBusGameModel.id == game_id).first()
        )
        if game_orm:
            game_orm.status = "cashed_out"
            game_orm.last_updated_timestamp = now

    logger.info(f"RTB game {game_id}: cashed out at {game.current_multiplier}x for {payout} spins")
    return get_game_by_id(game_id), payout, None
