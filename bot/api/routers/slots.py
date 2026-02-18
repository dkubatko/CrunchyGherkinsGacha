"""
Slots-related API endpoints.

This module contains all endpoints for slot machine operations including:
- Getting and consuming spins
- Verifying slot spin results
- Handling slot victories and claim wins
"""

import asyncio
import logging
import random
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.background_tasks import process_slots_victory_background
from api.config import DEBUG_MODE, TELEGRAM_TOKEN, gemini_util
from api.dependencies import get_validated_user, validate_user_in_chat, verify_user_match
from api.helpers import generate_slot_loss_pattern, normalize_rarity
from api.schemas import (
    ConsumeSpinResponse,
    DailyBonusClaimResponse,
    DailyBonusStatusResponse,
    MegaspinInfo,
    SlotSymbolInfo,
    SlotsClaimWinRequest,
    SlotsClaimWinResponse,
    SlotsVictoryRequest,
    SlotVerifyRequest,
    SlotVerifyResponse,
    SpinsRequest,
    SpinsResponse,
)
from settings.constants import SLOT_CLAIM_CHANCE, SLOT_WIN_CHANCE
from utils.rolling import get_random_rarity
from utils.services import (
    character_service,
    claim_service,
    spin_service,
    user_service,
    event_service,
)
from utils.events import EventType, SpinOutcome, MegaspinOutcome

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/slots", tags=["slots"])


@router.get("/spins", response_model=SpinsResponse)
async def get_user_spins(
    user_id: int = Query(..., description="User ID"),
    chat_id: str = Query(..., description="Chat ID"),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get the current number of spins for a user in a specific chat."""
    try:
        # Verify the authenticated user matches the requested user_id
        await verify_user_match(user_id, validated_user)
        await validate_user_in_chat(user_id, chat_id)

        # Get current spin count (no auto-grant; daily bonus is claimed explicitly)
        spins_count = await asyncio.to_thread(spin_service.get_user_spin_count, user_id, chat_id)

        # Get megaspin info
        megaspins_data = await asyncio.to_thread(spin_service.get_user_megaspins, user_id, chat_id)
        total_spins_required = spin_service._get_spins_for_megaspin()
        megaspin_info = MegaspinInfo(
            spins_until_megaspin=megaspins_data.spins_until_megaspin,
            total_spins_required=total_spins_required,
            megaspin_available=megaspins_data.megaspin_available,
        )

        return SpinsResponse(
            spins=spins_count,
            success=True,
            megaspin=megaspin_info,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error getting spins for user {user_id} in chat {chat_id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to get spins")


@router.get("/daily-bonus", response_model=DailyBonusStatusResponse)
async def get_daily_bonus_status(
    user_id: int = Query(..., description="User ID"),
    chat_id: str = Query(..., description="Chat ID"),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Check if the daily login bonus is available for a user."""
    try:
        await verify_user_match(user_id, validated_user)
        await validate_user_in_chat(user_id, chat_id)

        status = await asyncio.to_thread(spin_service.get_daily_bonus_status, user_id, chat_id)

        return DailyBonusStatusResponse(
            available=status["available"],
            current_streak=status["current_streak"],
            spins_to_grant=status["spins_to_grant"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error checking daily bonus for user {user_id} in chat {chat_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to check daily bonus")


@router.post("/daily-bonus/claim", response_model=DailyBonusClaimResponse)
async def claim_daily_bonus(
    request: SpinsRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Claim the daily login bonus for a user."""
    try:
        await verify_user_match(request.user_id, validated_user)
        await validate_user_in_chat(request.user_id, request.chat_id)

        result = await asyncio.to_thread(
            spin_service.claim_daily_bonus, request.user_id, request.chat_id
        )

        return DailyBonusClaimResponse(
            success=result["success"],
            spins_granted=result["spins_granted"],
            new_streak=result["new_streak"],
            total_spins=result["total_spins"],
            message=result["message"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error claiming daily bonus for user {request.user_id} in chat {request.chat_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to claim daily bonus")


@router.post("/spins", response_model=ConsumeSpinResponse)
async def consume_user_spin(
    request: SpinsRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Consume one spin for a user in a specific chat."""
    try:
        # Verify the authenticated user matches the requested user_id
        await verify_user_match(request.user_id, validated_user)
        await validate_user_in_chat(request.user_id, request.chat_id)

        # Attempt to consume a spin
        success = await asyncio.to_thread(
            spin_service.consume_user_spin, request.user_id, request.chat_id
        )

        if success:
            # Update megaspin counter (decrement by 1)
            megaspins_data = await asyncio.to_thread(
                spin_service.decrement_megaspin_counter, request.user_id, request.chat_id
            )
            total_spins_required = spin_service._get_spins_for_megaspin()
            megaspin_info = MegaspinInfo(
                spins_until_megaspin=megaspins_data.spins_until_megaspin,
                total_spins_required=total_spins_required,
                megaspin_available=megaspins_data.megaspin_available,
            )

            # Get remaining spins after consumption
            remaining_spins = await asyncio.to_thread(
                spin_service.get_user_spin_count,
                request.user_id,
                request.chat_id,
            )

            return ConsumeSpinResponse(
                success=True,
                spins_remaining=remaining_spins,
                message="Spin consumed successfully",
                megaspin=megaspin_info,
            )
        else:
            # Get current spins to show in error
            current_spins = await asyncio.to_thread(
                spin_service.get_user_spin_count,
                request.user_id,
                request.chat_id,
            )

            # Get current megaspin info
            megaspins_data = await asyncio.to_thread(
                spin_service.get_user_megaspins, request.user_id, request.chat_id
            )
            total_spins_required = spin_service._get_spins_for_megaspin()
            megaspin_info = MegaspinInfo(
                spins_until_megaspin=megaspins_data.spins_until_megaspin,
                total_spins_required=total_spins_required,
                megaspin_available=megaspins_data.megaspin_available,
            )

            return ConsumeSpinResponse(
                success=False,
                spins_remaining=current_spins,
                message="No spins available",
                megaspin=megaspin_info,
            )

    except Exception as e:
        logger.error(
            f"Error consuming spin for user {request.user_id} in chat {request.chat_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to consume spin")


@router.post("/megaspin", response_model=ConsumeSpinResponse)
async def consume_megaspin(
    request: SpinsRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Consume a megaspin for a user in a specific chat. Megaspins are guaranteed wins."""
    try:
        # Verify the authenticated user matches the requested user_id
        await verify_user_match(request.user_id, validated_user)
        await validate_user_in_chat(request.user_id, request.chat_id)

        # Attempt to consume the megaspin
        success = await asyncio.to_thread(
            spin_service.consume_megaspin, request.user_id, request.chat_id
        )

        # Get updated megaspin info
        megaspins_data = await asyncio.to_thread(
            spin_service.get_user_megaspins, request.user_id, request.chat_id
        )
        total_spins_required = spin_service._get_spins_for_megaspin()
        megaspin_info = MegaspinInfo(
            spins_until_megaspin=megaspins_data.spins_until_megaspin,
            total_spins_required=total_spins_required,
            megaspin_available=megaspins_data.megaspin_available,
        )

        if success:
            return ConsumeSpinResponse(
                success=True,
                spins_remaining=None,  # Megaspin doesn't affect regular spin count
                message="Megaspin consumed successfully",
                megaspin=megaspin_info,
            )
        else:
            return ConsumeSpinResponse(
                success=False,
                spins_remaining=None,
                message="No megaspin available",
                megaspin=megaspin_info,
            )

    except Exception as e:
        logger.error(
            f"Error consuming megaspin for user {request.user_id} in chat {request.chat_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to consume megaspin")


@router.post("/verify", response_model=SlotVerifyResponse)
async def verify_slot_spin(
    request: SlotVerifyRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Verify a slot spin result using server-side randomness and logic."""
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(request.user_id, validated_user)
    await validate_user_in_chat(request.user_id, request.chat_id)
    # Validate input parameters
    if not request.symbols or len(request.symbols) == 0:
        raise HTTPException(status_code=400, detail="Symbols list cannot be empty")

    symbol_count = len(request.symbols)

    if request.random_number < 0 or request.random_number >= symbol_count:
        raise HTTPException(
            status_code=400,
            detail=f"Random number must be between 0 and {symbol_count - 1}",
        )

    try:
        # Use current time and client random number for better entropy
        # Don't set a deterministic seed - let Python use system randomness
        random.seed()  # Reset to system randomness

        # Add some entropy from the request for security
        entropy_source = hash(
            f"{request.user_id}_{request.chat_id}_{request.random_number}_{time.time()}"
        )
        random.seed(entropy_source)

        # Server-side win rate from config (boosted in debug mode)
        win_chance = 0.2 if DEBUG_MODE else SLOT_WIN_CHANCE
        is_card_win = random.random() < win_chance
        rarity: Optional[str] = None
        winning_symbol: Optional[SlotSymbolInfo] = None
        slot_results: List[SlotSymbolInfo] = []
        is_win = False

        if is_card_win:
            # Player wins a card - select a random user or character symbol
            # Filter out claim symbols for card wins
            eligible_symbols = [s for s in request.symbols if s.type != "claim"]

            if not eligible_symbols:
                # Fallback: no eligible symbols, treat as loss
                is_card_win = False
            else:
                # Pick a random eligible symbol
                winning_symbol = random.choice(eligible_symbols)
                rarity = get_random_rarity(source="slots")
                # All three reels show the winning symbol
                slot_results = [winning_symbol, winning_symbol, winning_symbol]
                is_win = True

        if not is_card_win:
            # Check for claim win (only if they didn't win a card)
            claim_chance = 0.5 if DEBUG_MODE else SLOT_CLAIM_CHANCE
            claim_win = random.random() < claim_chance

            if claim_win:
                # Find the claim symbol
                claim_symbols = [s for s in request.symbols if s.type == "claim"]
                if claim_symbols:
                    winning_symbol = claim_symbols[0]  # Should only be one claim symbol
                    # All three reels show the claim symbol
                    slot_results = [winning_symbol, winning_symbol, winning_symbol]
                    is_win = True  # Claim win is still a win!

        # Generate loss pattern if no win
        if not slot_results:
            slot_results = generate_slot_loss_pattern(random, request.symbols)

        # Build descriptive log message
        if is_card_win and rarity:
            win_type = f"card ({rarity})"
        elif winning_symbol and winning_symbol.type == "claim":
            win_type = "claim point"
        else:
            win_type = "loss"

        logger.info(
            f"Slot verification for user {request.user_id} in chat {request.chat_id}: "
            f"result={win_type}, win_chance={win_chance:.3f}, "
            f"winning_symbol={winning_symbol}, slot_results={[f'{s.type}:{s.id}' for s in slot_results]}"
        )

        # Log spin event (card wins are logged after successful generation in background task)
        if is_card_win and rarity:
            # Card win events are logged in process_slots_victory_background after card generation
            pass
        elif winning_symbol and winning_symbol.type == "claim":
            event_service.log(
                EventType.SPIN,
                SpinOutcome.CLAIM_WIN,
                user_id=request.user_id,
                chat_id=request.chat_id,
            )
        else:
            event_service.log(
                EventType.SPIN,
                SpinOutcome.LOSS,
                user_id=request.user_id,
                chat_id=request.chat_id,
            )

        return SlotVerifyResponse(is_win=is_win, slot_results=slot_results, rarity=rarity)

    except Exception as e:
        logger.error(
            f"Error verifying slot spin for user {request.user_id} in chat {request.chat_id}: {e}"
        )
        # Log spin error
        event_service.log(
            EventType.SPIN,
            SpinOutcome.ERROR,
            user_id=request.user_id,
            chat_id=request.chat_id,
            error_message=str(e),
        )
        raise HTTPException(status_code=500, detail="Failed to verify slot spin")


@router.post("/megaspin/verify", response_model=SlotVerifyResponse)
async def verify_megaspin(
    request: SlotVerifyRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Verify a megaspin result - guaranteed card win."""
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(request.user_id, validated_user)
    await validate_user_in_chat(request.user_id, request.chat_id)

    # Validate input parameters
    if not request.symbols or len(request.symbols) == 0:
        raise HTTPException(status_code=400, detail="Symbols list cannot be empty")

    try:
        random.seed()  # Reset to system randomness

        # Filter out claim symbols - megaspins only give cards
        eligible_symbols = [s for s in request.symbols if s.type != "claim"]

        if not eligible_symbols:
            raise HTTPException(status_code=400, detail="No eligible symbols for megaspin")

        # Pick a random eligible symbol - guaranteed win
        winning_symbol = random.choice(eligible_symbols)
        rarity = get_random_rarity(source="slots")

        # All three reels show the winning symbol
        slot_results = [winning_symbol, winning_symbol, winning_symbol]

        logger.info(
            f"Megaspin verification for user {request.user_id} in chat {request.chat_id}: "
            f"rarity={rarity}, winning_symbol={winning_symbol.type}:{winning_symbol.id}"
        )

        # Megaspin success event is logged in process_slots_victory_background after card generation

        return SlotVerifyResponse(is_win=True, slot_results=slot_results, rarity=rarity)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error verifying megaspin for user {request.user_id} in chat {request.chat_id}: {e}"
        )
        # Log megaspin error
        event_service.log(
            EventType.MEGASPIN,
            MegaspinOutcome.ERROR,
            user_id=request.user_id,
            chat_id=request.chat_id,
            error_message=str(e),
        )
        raise HTTPException(status_code=500, detail="Failed to verify megaspin")


@router.post("/victory")
async def slots_victory(
    request: SlotsVictoryRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Handle a slot victory by generating a card and sharing it in the chat."""
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(request.user_id, validated_user)

    # Extract user data from validated data
    user_data: Dict[str, Any] = validated_user["user"] or {}
    auth_user_id = user_data.get("id")

    # Get username
    username = user_data.get("username")
    if not username:
        username = await asyncio.to_thread(user_service.get_username_for_user_id, auth_user_id)
    if not username:
        logger.warning("Unable to resolve username for user_id %s", auth_user_id)
        raise HTTPException(status_code=400, detail="Username not found for user")

    # Validate request parameters
    normalized_rarity = normalize_rarity(request.rarity)
    if not normalized_rarity:
        logger.warning("Unsupported rarity '%s' provided", request.rarity)
        raise HTTPException(status_code=400, detail="Unsupported rarity value")

    chat_id = str(request.chat_id).strip()
    if not chat_id:
        logger.warning("Empty chat_id provided for slots victory")
        raise HTTPException(status_code=400, detail="chat_id is required")

    source_type = (request.source.type or "").strip().lower()
    if source_type not in ("user", "character"):
        logger.warning("Unsupported source type '%s'", request.source.type)
        raise HTTPException(status_code=400, detail="Invalid source type")

    if not TELEGRAM_TOKEN:
        logger.error("Bot token not available for slots victory")
        raise HTTPException(status_code=503, detail="Bot service unavailable")

    # Validate chat exists and user is enrolled
    await validate_user_in_chat(request.user_id, chat_id)

    # Get source display name for validation
    if source_type == "user":
        source_user = await asyncio.to_thread(user_service.get_user, request.source.id)
        if not source_user or not source_user.display_name:
            raise HTTPException(status_code=404, detail="Source user not found or incomplete")
        display_name = source_user.display_name
    else:
        source_character = await asyncio.to_thread(
            character_service.get_character_by_id, request.source.id
        )
        if not source_character or not source_character.name:
            raise HTTPException(status_code=404, detail="Source character not found")
        if str(source_character.chat_id) != chat_id:
            raise HTTPException(status_code=400, detail="Character does not belong to chat")
        display_name = source_character.name

    # All validation passed - respond immediately with success
    response_data = {
        "status": "processing",
        "message": "Slots victory accepted, processing card...",
    }

    # Process card generation in background task (fire-and-forget)
    asyncio.create_task(
        process_slots_victory_background(
            bot_token=TELEGRAM_TOKEN,
            debug_mode=DEBUG_MODE,
            username=username,
            normalized_rarity=normalized_rarity,
            display_name=display_name,
            chat_id=chat_id,
            source_type=source_type,
            source_id=request.source.id,
            user_id=request.user_id,
            gemini_util_instance=gemini_util,
            is_megaspin=request.is_megaspin,
        )
    )

    return response_data


@router.post("/claim-win", response_model=SlotsClaimWinResponse)
async def slots_claim_win(
    request: SlotsClaimWinRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Handle a slot claim win by adding 1 claim point to the user's balance."""
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(request.user_id, validated_user)

    chat_id = str(request.chat_id).strip()
    if not chat_id:
        logger.warning("Empty chat_id provided for slots claim win")
        raise HTTPException(status_code=400, detail="chat_id is required")

    # Validate chat exists and user is enrolled
    await validate_user_in_chat(request.user_id, chat_id)

    try:
        # Add claim points to the user's balance
        amount = max(1, request.amount)  # Ensure at least 1 point is added
        new_balance = await asyncio.to_thread(
            claim_service.increment_claim_balance, request.user_id, chat_id, amount
        )

        logger.info(
            "User %s won %s claim point(s) in chat %s. New balance: %s",
            request.user_id,
            amount,
            chat_id,
            new_balance,
        )

        return SlotsClaimWinResponse(
            success=True,
            balance=new_balance,
        )

    except Exception as exc:
        logger.error(
            "Error adding claim point for user %s in chat %s: %s",
            request.user_id,
            chat_id,
            exc,
        )
        raise HTTPException(status_code=500, detail="Failed to add claim point")
