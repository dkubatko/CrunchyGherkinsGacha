"""Ride the Bus (RTB) game API endpoints."""

import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.background_tasks import process_rtb_result_notification
from api.dependencies import get_validated_user, verify_user_match
from api.helpers import format_timestamp
from api.schemas import (
    RTBCardInfo,
    RTBCashOutRequest,
    RTBCashOutResponse,
    RTBGameResponse,
    RTBGuessRequest,
    RTBGuessResponse,
    RTBStartRequest,
)
from utils.services import (
    rtb_create_game,
    rtb_cash_out,
    rtb_get_active_game,
    rtb_get_game_by_id,
    rtb_process_guess,
    RTB_MIN_BET,
    RTB_MAX_BET,
    RTB_MULTIPLIER_PROGRESSION,
    RARITY_ORDER,
    user_service,
    card_service,
    spin_service,
)
from utils.schemas import RideTheBusGame

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rtb", tags=["rtb"])


def _build_game_response(
    game: RideTheBusGame, spins_balance: Optional[int] = None
) -> RTBGameResponse:
    """Build RTBGameResponse from game state."""
    # Only reveal all cards if the player won (completed all cards)
    # For lost/cashed_out, only show cards up to current_position
    reveal_all = game.status == "won"
    # For lost games, also reveal the card they lost on (current_position)
    reveal_up_to = game.current_position + 1 if game.status == "lost" else game.current_position
    cards = []

    for i, (card_id, rarity, title) in enumerate(
        zip(game.card_ids, game.card_rarities, game.card_titles)
    ):
        is_revealed = i < reveal_up_to or reveal_all
        if is_revealed:
            image_b64 = card_service.get_card_image(card_id)
            cards.append(
                RTBCardInfo(
                    card_id=card_id,
                    rarity=rarity,
                    title=title,
                    image_b64=image_b64,
                )
            )
        else:
            cards.append(RTBCardInfo(card_id=card_id, rarity="???", title="???", image_b64=None))

    next_pos = game.current_position + 1
    return RTBGameResponse(
        game_id=game.id,
        status=game.status,
        bet_amount=game.bet_amount,
        current_position=game.current_position,
        current_multiplier=game.current_multiplier,
        next_multiplier=RTB_MULTIPLIER_PROGRESSION.get(next_pos, game.current_multiplier),
        potential_payout=game.bet_amount * game.current_multiplier,
        cards=cards,
        started_timestamp=format_timestamp(game.started_timestamp),
        last_updated_timestamp=format_timestamp(game.last_updated_timestamp),
        spins_balance=spins_balance,
    )


async def _verify_user_in_chat(user_id: int, chat_id: str, validated_user: Dict[str, Any]):
    """Verify user auth and chat membership."""
    await verify_user_match(user_id, validated_user)
    chat_id = str(chat_id).strip()
    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id is required")
    if not await asyncio.to_thread(user_service.is_user_in_chat, chat_id, user_id):
        raise HTTPException(status_code=403, detail="User not enrolled in this chat")
    return chat_id


async def _get_spins_balance(user_id: int, chat_id: str) -> int:
    return await asyncio.to_thread(
        spin_service.get_or_update_user_spins_with_daily_refresh, user_id, chat_id
    )


@router.get("/game", response_model=Optional[RTBGameResponse])
async def get_rtb_game(
    user_id: int = Query(...),
    chat_id: str = Query(...),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get the current active RTB game for a user in a chat."""
    chat_id = await _verify_user_in_chat(user_id, chat_id, validated_user)

    game = await asyncio.to_thread(rtb_get_active_game, user_id, chat_id)
    if not game:
        return None

    return _build_game_response(game, await _get_spins_balance(user_id, chat_id))


@router.post("/start", response_model=RTBGameResponse)
async def start_rtb_game(
    request: RTBStartRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Start a new RTB game. Requires enough spins for the bet (10-50)."""
    chat_id = await _verify_user_in_chat(request.user_id, request.chat_id, validated_user)

    if not (RTB_MIN_BET <= request.bet_amount <= RTB_MAX_BET):
        raise HTTPException(
            status_code=400, detail=f"Bet must be between {RTB_MIN_BET} and {RTB_MAX_BET} spins"
        )

    # Check and deduct spins
    current_spins = await _get_spins_balance(request.user_id, chat_id)
    if current_spins < request.bet_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough spins. You have {current_spins}, need {request.bet_amount}",
        )

    if not await asyncio.to_thread(
        spin_service.decrement_user_spins, request.user_id, chat_id, request.bet_amount
    ):
        raise HTTPException(status_code=400, detail="Failed to deduct spins")

    # Create game
    game, error = await asyncio.to_thread(
        rtb_create_game, request.user_id, chat_id, request.bet_amount
    )
    if error or not game:
        await asyncio.to_thread(
            spin_service.increment_user_spins, request.user_id, chat_id, request.bet_amount
        )
        raise HTTPException(status_code=400, detail=error or "Failed to create game")

    return _build_game_response(game, await _get_spins_balance(request.user_id, chat_id))


@router.post("/guess", response_model=RTBGuessResponse)
async def make_rtb_guess(
    request: RTBGuessRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Make a guess in an RTB game (higher, lower, or equal)."""
    await verify_user_match(request.user_id, validated_user)

    guess = request.guess.lower().strip()
    if guess not in ("higher", "lower", "equal"):
        raise HTTPException(
            status_code=400, detail="Invalid guess. Must be 'higher', 'lower', or 'equal'"
        )

    # Validate game ownership
    game = await asyncio.to_thread(rtb_get_game_by_id, request.game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.user_id != request.user_id:
        raise HTTPException(status_code=403, detail="Not your game")
    if game.status != "active":
        raise HTTPException(status_code=400, detail=f"Game is not active (status: {game.status})")

    # Calculate actual comparison before processing
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

    # Process guess
    updated_game, correct, error = await asyncio.to_thread(
        rtb_process_guess, request.game_id, guess
    )
    if error or not updated_game:
        raise HTTPException(status_code=400, detail=error or "Failed to process guess")

    # Award winnings if won
    if correct and updated_game.status == "won":
        payout = updated_game.bet_amount * updated_game.current_multiplier
        await asyncio.to_thread(
            spin_service.increment_user_spins, request.user_id, updated_game.chat_id, payout
        )
        message = f"🎉 Correct! You won {payout} spins!"
        # Send win notification
        username = await asyncio.to_thread(user_service.get_username_for_user_id, request.user_id)
        if username:
            asyncio.create_task(
                process_rtb_result_notification(
                    username=username,
                    chat_id=updated_game.chat_id,
                    result="won",
                    amount=payout,
                    multiplier=updated_game.current_multiplier,
                )
            )
    elif correct:
        message = f"✅ Correct! Next card is {actual}. Multiplier is now {updated_game.current_multiplier}x!"
    else:
        message = f"❌ Wrong! Next card was {actual}. You lost {updated_game.bet_amount} spins."
        # Send loss notification
        username = await asyncio.to_thread(user_service.get_username_for_user_id, request.user_id)
        if username:
            asyncio.create_task(
                process_rtb_result_notification(
                    username=username,
                    chat_id=updated_game.chat_id,
                    result="lost",
                    amount=updated_game.bet_amount,
                    multiplier=updated_game.current_multiplier,
                )
            )

    return RTBGuessResponse(
        correct=correct,
        game=_build_game_response(
            updated_game, await _get_spins_balance(request.user_id, updated_game.chat_id)
        ),
        actual_comparison=actual,
        message=message,
    )


@router.post("/cashout", response_model=RTBCashOutResponse)
async def cash_out_rtb_game(
    request: RTBCashOutRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Cash out of an active RTB game to take current winnings."""
    await verify_user_match(request.user_id, validated_user)

    # Validate game
    game = await asyncio.to_thread(rtb_get_game_by_id, request.game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.user_id != request.user_id:
        raise HTTPException(status_code=403, detail="Not your game")
    if game.status != "active":
        raise HTTPException(status_code=400, detail=f"Game is not active (status: {game.status})")
    if game.current_position < 2:
        raise HTTPException(
            status_code=400, detail="Cannot cash out before making at least one correct guess"
        )

    # Process cash out
    updated_game, payout, error = await asyncio.to_thread(rtb_cash_out, request.game_id)
    if error or not updated_game:
        raise HTTPException(status_code=400, detail=error or "Failed to cash out")

    await asyncio.to_thread(
        spin_service.increment_user_spins, request.user_id, updated_game.chat_id, payout
    )

    # Send cashout notification
    username = await asyncio.to_thread(user_service.get_username_for_user_id, request.user_id)
    if username:
        asyncio.create_task(
            process_rtb_result_notification(
                username=username,
                chat_id=updated_game.chat_id,
                result="cashed out",
                amount=payout,
                multiplier=updated_game.current_multiplier,
            )
        )

    return RTBCashOutResponse(
        success=True,
        payout=payout,
        new_spin_total=await _get_spins_balance(request.user_id, updated_game.chat_id),
        message=f"💰 Cashed out for {payout} spins ({updated_game.current_multiplier}x multiplier)!",
        game=_build_game_response(
            updated_game, await _get_spins_balance(request.user_id, updated_game.chat_id)
        ),
    )


@router.get("/config")
async def get_rtb_config(
    chat_id: Optional[str] = Query(None),
):
    """Get RTB game configuration and availability."""
    from utils.services import rtb_check_availability

    config = {
        "min_bet": RTB_MIN_BET,
        "max_bet": RTB_MAX_BET,
        "cards_per_game": 5,
        "multiplier_progression": RTB_MULTIPLIER_PROGRESSION,
        "rarity_order": RARITY_ORDER,
    }

    # If chat_id provided, check availability
    if chat_id:
        is_available, reason = await asyncio.to_thread(rtb_check_availability, chat_id)
        config["available"] = is_available
        config["unavailable_reason"] = reason
    else:
        config["available"] = True
        config["unavailable_reason"] = None

    return config
