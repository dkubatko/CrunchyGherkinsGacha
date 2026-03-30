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

from api.background_tasks import (
    process_slots_victory_background,
    process_slot_aspect_victory_background,
)
from api.config import DEBUG_MODE, TELEGRAM_TOKEN, gemini_util
from api.dependencies import get_validated_user, validate_user_in_chat, verify_user_match
from api.helpers import generate_slot_loss_pattern, normalize_rarity
from api.schemas import (
    ConsumeSpinResponse,
    DailyBonusClaimResponse,
    DailyBonusStatusResponse,
    MegaspinInfo,
    SlotSymbolInfo,
    SlotSymbolSummary,
    SlotsClaimWinRequest,
    SlotsClaimWinResponse,
    SlotsVictoryRequest,
    SlotsVictoryResponse,
    SlotVerifyRequest,
    SlotVerifyResponse,
    SpinsRequest,
    SpinsResponse,
)
from settings.constants import SLOT_ASPECT_WIN_CHANCE, SLOT_CLAIM_CHANCE, SLOT_WIN_CHANCE
from utils.rolling import get_random_rarity
from repos import character_repo
from repos import claim_repo
from repos import aspect_repo
from repos import set_icon_repo
from repos import set_repo
from repos import spin_repo
from repos import user_repo
from managers import event_manager
from managers import spin_manager
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
        spins_count = await asyncio.to_thread(spin_repo.get_user_spin_count, user_id, chat_id)

        # Get megaspin info
        megaspins_data = await asyncio.to_thread(spin_repo.get_user_megaspins, user_id, chat_id)
        total_spins_required = spin_repo._get_spins_for_megaspin()
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

        status = await asyncio.to_thread(spin_manager.get_daily_bonus_status, user_id, chat_id)

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
            spin_manager.claim_daily_bonus, request.user_id, request.chat_id
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
            spin_repo.consume_user_spin, request.user_id, request.chat_id
        )

        if success:
            # Update megaspin counter (decrement by 1)
            megaspins_data = await asyncio.to_thread(
                spin_manager.decrement_megaspin_counter, request.user_id, request.chat_id
            )
            total_spins_required = spin_repo._get_spins_for_megaspin()
            megaspin_info = MegaspinInfo(
                spins_until_megaspin=megaspins_data.spins_until_megaspin,
                total_spins_required=total_spins_required,
                megaspin_available=megaspins_data.megaspin_available,
            )

            # Get remaining spins after consumption
            remaining_spins = await asyncio.to_thread(
                spin_repo.get_user_spin_count,
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
                spin_repo.get_user_spin_count,
                request.user_id,
                request.chat_id,
            )

            # Get current megaspin info
            megaspins_data = await asyncio.to_thread(
                spin_repo.get_user_megaspins, request.user_id, request.chat_id
            )
            total_spins_required = spin_repo._get_spins_for_megaspin()
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
            spin_repo.consume_megaspin, request.user_id, request.chat_id
        )

        # Get updated megaspin info
        megaspins_data = await asyncio.to_thread(
            spin_repo.get_user_megaspins, request.user_id, request.chat_id
        )
        total_spins_required = spin_repo._get_spins_for_megaspin()
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


@router.get("/set-symbols", response_model=List[SlotSymbolSummary])
async def get_set_symbols(
    chat_id: str = Query(..., description="Chat ID"),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Return set icons for the slot reel symbol strip.

    Returns active sets (source "all" or "slots") that have a generated slot
    icon, formatted as SlotSymbolSummary with type="set".
    """
    try:
        eligible_sets = await asyncio.to_thread(set_repo.get_eligible_sets_for_slots)
        if not eligible_sets:
            return []

        icons = await asyncio.to_thread(set_icon_repo.get_all_icons_b64)

        symbols: List[SlotSymbolSummary] = []
        for s in eligible_sets:
            icon_b64 = icons.get(s.id)
            if not icon_b64:
                continue
            symbols.append(
                SlotSymbolSummary(
                    id=s.id,
                    display_name=s.name,
                    slot_icon_b64=icon_b64,
                    type="set",
                )
            )
        return symbols
    except Exception as e:
        logger.error(f"Error loading set symbols for chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load set symbols")


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
        random.seed()
        entropy_source = hash(
            f"{request.user_id}_{request.chat_id}_{request.random_number}_{time.time()}"
        )
        random.seed(entropy_source)

        # Partition symbols by type — each win branch picks only from its own pool
        card_symbols = [s for s in request.symbols if s.type in ("user", "character")]
        set_symbols = [s for s in request.symbols if s.type == "set"]
        claim_symbols = [s for s in request.symbols if s.type == "claim"]

        winning_symbol: Optional[SlotSymbolInfo] = None
        slot_results: List[SlotSymbolInfo] = []
        rarity: Optional[str] = None
        win_type: Optional[str] = None
        chosen_set_id: Optional[int] = None
        chosen_set_name: Optional[str] = None

        # Roll 1: Card win
        card_chance = 0.2 if DEBUG_MODE else SLOT_WIN_CHANCE
        if random.random() < card_chance and card_symbols:
            winning_symbol = random.choice(card_symbols)
            rarity = get_random_rarity(source="slots")
            win_type = "card"

        # Roll 2: Aspect win (only if card didn't win)
        if not win_type:
            aspect_chance = 0.3 if DEBUG_MODE else SLOT_ASPECT_WIN_CHANCE
            if random.random() < aspect_chance and set_symbols:
                rarity = get_random_rarity(source="slots")
                try:
                    defs_by_rarity = await asyncio.to_thread(
                        aspect_repo.get_aspect_definitions_by_rarity,
                        source="slots",
                    )
                    eligible_ids = {d.set_id for d in defs_by_rarity.get(rarity, [])}
                    eligible = [s for s in set_symbols if s.id in eligible_ids]
                    if eligible:
                        winning_symbol = random.choice(eligible)
                        chosen_set_id = winning_symbol.id
                        chosen_set_name = next(
                            (d.set_name.title() for d in defs_by_rarity.get(rarity, []) if d.set_id == chosen_set_id),
                            None,
                        )
                        win_type = "aspect"
                    else:
                        rarity = None  # No eligible sets for this rarity — fall through
                except Exception as e:
                    logger.warning("Failed to pick set for aspect win: %s", e)
                    rarity = None

        # Roll 3: Claim win (only if no card/aspect win)
        if not win_type:
            claim_chance = 0.5 if DEBUG_MODE else SLOT_CLAIM_CHANCE
            if random.random() < claim_chance and claim_symbols:
                winning_symbol = claim_symbols[0]
                win_type = "claim"

        # Build results
        if winning_symbol:
            slot_results = [winning_symbol, winning_symbol, winning_symbol]
        else:
            slot_results = generate_slot_loss_pattern(random, request.symbols)

        # Logging
        win_type_log = (
            f"{win_type} ({rarity})" if win_type in ("card", "aspect") and rarity
            else win_type or "loss"
        )
        logger.info(
            "Slot verification for user %s in chat %s: result=%s",
            request.user_id, request.chat_id, win_type_log,
        )

        # Event logging (card/aspect wins logged after generation in background task)
        if win_type == "claim":
            event_manager.log(
                EventType.SPIN, SpinOutcome.CLAIM_WIN,
                user_id=request.user_id, chat_id=request.chat_id,
            )
        elif not win_type:
            event_manager.log(
                EventType.SPIN, SpinOutcome.LOSS,
                user_id=request.user_id, chat_id=request.chat_id,
            )

        return SlotVerifyResponse(
            is_win=win_type is not None,
            slot_results=slot_results,
            rarity=rarity,
            win_type=win_type,
            set_id=chosen_set_id,
            set_name=chosen_set_name,
        )

    except Exception as e:
        logger.error(
            f"Error verifying slot spin for user {request.user_id} in chat {request.chat_id}: {e}"
        )
        # Log spin error
        event_manager.log(
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

        # Filter out claim symbols - megaspins don't give claim points
        eligible_symbols = [s for s in request.symbols if s.type != "claim"]

        if not eligible_symbols:
            raise HTTPException(status_code=400, detail="No eligible symbols for megaspin")

        # Pick a random eligible symbol - guaranteed win
        winning_symbol = random.choice(eligible_symbols)
        rarity = get_random_rarity(source="slots")

        # All three reels show the winning symbol
        slot_results = [winning_symbol, winning_symbol, winning_symbol]

        # Determine win type based on the symbol picked
        win_type: str = "card"
        chosen_set_id: Optional[int] = None
        chosen_set_name: Optional[str] = None

        if winning_symbol.type == "set":
            win_type = "aspect"
            chosen_set_id = winning_symbol.id
            # Simple name lookup — rarity/definition validation
            # happens downstream in the background task, same as cards
            try:
                set_obj = await asyncio.to_thread(set_repo.get_set, chosen_set_id)
                if set_obj:
                    chosen_set_name = set_obj.name.title() if set_obj.name else None
            except Exception as e:
                logger.warning("Megaspin set name lookup failed: %s", e)

        logger.info(
            f"Megaspin verification for user {request.user_id} in chat {request.chat_id}: "
            f"rarity={rarity}, win_type={win_type}, winning_symbol={winning_symbol.type}:{winning_symbol.id}"
        )

        # Megaspin success event is logged in background after generation

        return SlotVerifyResponse(
            is_win=True,
            slot_results=slot_results,
            rarity=rarity,
            win_type=win_type,
            set_id=chosen_set_id,
            set_name=chosen_set_name,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error verifying megaspin for user {request.user_id} in chat {request.chat_id}: {e}"
        )
        # Log megaspin error
        event_manager.log(
            EventType.MEGASPIN,
            MegaspinOutcome.ERROR,
            user_id=request.user_id,
            chat_id=request.chat_id,
            error_message=str(e),
        )
        raise HTTPException(status_code=500, detail="Failed to verify megaspin")


@router.post("/victory", response_model=SlotsVictoryResponse)
async def slots_victory(
    request: SlotsVictoryRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Handle a slot card or aspect victory.

    Dispatches to the appropriate background task based on ``win_type``.
    """
    await verify_user_match(request.user_id, validated_user)

    user_data: Dict[str, Any] = validated_user["user"] or {}
    auth_user_id = user_data.get("id")

    # --- shared validation ---------------------------------------------------
    username = user_data.get("username")
    if not username:
        username = await asyncio.to_thread(user_repo.get_username_for_user_id, auth_user_id)
    if not username:
        raise HTTPException(status_code=400, detail="Username not found for user")

    normalized_rarity = normalize_rarity(request.rarity)
    if not normalized_rarity:
        raise HTTPException(status_code=400, detail="Unsupported rarity value")

    chat_id = str(request.chat_id).strip()
    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id is required")

    if not TELEGRAM_TOKEN:
        raise HTTPException(status_code=503, detail="Bot service unavailable")

    await validate_user_in_chat(request.user_id, chat_id)

    # --- dispatch by win_type ------------------------------------------------
    if request.win_type == "card":
        source_type = (request.source_type or "").strip().lower()
        if source_type not in ("user", "character"):
            raise HTTPException(status_code=400, detail="Invalid source type")

        if source_type == "user":
            source_user = await asyncio.to_thread(user_repo.get_user, request.source_id)
            if not source_user or not source_user.display_name:
                raise HTTPException(status_code=404, detail="Source user not found or incomplete")
            display_name = source_user.display_name
        else:
            source_character = await asyncio.to_thread(
                character_repo.get_character_by_id, request.source_id
            )
            if not source_character or not source_character.name:
                raise HTTPException(status_code=404, detail="Source character not found")
            if str(source_character.chat_id) != chat_id:
                raise HTTPException(status_code=400, detail="Character does not belong to chat")
            display_name = source_character.name

        asyncio.create_task(
            process_slots_victory_background(
                bot_token=TELEGRAM_TOKEN,
                debug_mode=DEBUG_MODE,
                username=username,
                normalized_rarity=normalized_rarity,
                display_name=display_name,
                chat_id=chat_id,
                source_type=source_type,
                source_id=request.source_id,
                user_id=request.user_id,
                gemini_util_instance=gemini_util,
                is_megaspin=request.is_megaspin,
            )
        )
        return SlotsVictoryResponse(status="processing", message="Card generation started")

    elif request.win_type == "aspect":
        asyncio.create_task(
            process_slot_aspect_victory_background(
                bot_token=TELEGRAM_TOKEN,
                debug_mode=DEBUG_MODE,
                username=username,
                normalized_rarity=normalized_rarity,
                chat_id=chat_id,
                user_id=request.user_id,
                gemini_util_instance=gemini_util,
                set_id=request.set_id,
            )
        )
        return SlotsVictoryResponse(status="processing", message="Aspect generation started")

    else:
        raise HTTPException(status_code=400, detail="Invalid win_type; expected 'card' or 'aspect'")


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
        new_balance = await asyncio.to_thread(
            claim_repo.increment_claim_balance, request.user_id, chat_id, 1
        )

        logger.info(
            "User %s won 1 claim point in chat %s. New balance: %s",
            request.user_id,
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
