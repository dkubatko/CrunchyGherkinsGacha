"""
Slots-related API endpoints.

This module contains all endpoints for slot machine operations including:
- Getting and consuming spins
- Verifying slot spin results
- Handling slot victories and claim wins
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.background_tasks import (
    process_slots_victory_background,
    process_slot_aspect_victory_background,
)
from api.config import DEBUG_MODE, TELEGRAM_TOKEN, gemini_util
from api.dependencies import get_validated_user, validate_user_in_chat, verify_user_match
from api.helpers import normalize_rarity
from api.schemas import (
    ConsumeSpinResponse,
    DailyBonusClaimResponse,
    DailyBonusStatusResponse,
    MegaspinInfo,
    SlotSpinRequest,
    SlotSpinResponse,
    SlotSymbolInfo,
    SlotSymbolSummary,
    SlotsClaimWinRequest,
    SlotsClaimWinResponse,
    SlotsVictoryRequest,
    SlotsVictoryResponse,
    SpinsRequest,
    SpinsResponse,
)
from settings.constants import (
    SLOT_ASPECT_WIN_CHANCE,
    SLOT_BET_MULTIPLIERS,
    SLOT_CARD_WIN_CHANCE,
    SLOT_CLAIM_CHANCE,
)
from repos import claim_repo
from repos import set_icon_repo
from repos import set_repo
from repos import spin_repo
from repos import spin_result_repo
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


@router.post("/spin", response_model=SlotSpinResponse)
async def spin_slots(
    request: SlotSpinRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Atomic slot spin — deducts ``multiplier`` spins and rolls the outcome.

    Replaces the previous ``POST /slots/spins`` (consume) +
    ``POST /slots/verify`` (compute) pair. The merged endpoint:

      * Validates the multiplier (must be in :data:`SLOT_BET_MULTIPLIERS`).
      * Atomically deducts ``multiplier`` spins (FOR UPDATE) and advances
        megaspin progress by the same amount (with carry-overflow).
      * Derives the slot symbol pool server-side (clients cannot bias it).
      * Rolls the outcome under the multi-spin distribution
        ``P(loss|N) = p_loss^N``; conditional win-type ratios unchanged.
      * For card/aspect wins, persists a ``SpinResult`` row whose id is
        returned to the client and later required by ``POST /slots/victory``.
    """
    await verify_user_match(request.user_id, validated_user)
    await validate_user_in_chat(request.user_id, request.chat_id)

    if request.multiplier not in SLOT_BET_MULTIPLIERS:
        raise HTTPException(
            status_code=400,
            detail=f"multiplier must be one of {SLOT_BET_MULTIPLIERS}",
        )

    try:
        result = await asyncio.to_thread(
            spin_manager.consume_and_roll,
            request.user_id,
            request.chat_id,
            request.multiplier,
            DEBUG_MODE,
        )
    except Exception as e:
        logger.error(
            "Error executing /slots/spin for user %s in chat %s: %s",
            request.user_id,
            request.chat_id,
            e,
            exc_info=True,
        )
        event_manager.log(
            EventType.SPIN,
            SpinOutcome.ERROR,
            user_id=request.user_id,
            chat_id=request.chat_id,
            multiplier=request.multiplier,
            error_message=str(e),
        )
        raise HTTPException(status_code=500, detail="Failed to spin")

    megaspins = result["megaspin"]
    total_required = spin_repo._get_spins_for_megaspin()
    megaspin_info = MegaspinInfo(
        spins_until_megaspin=megaspins.spins_until_megaspin,
        total_spins_required=total_required,
        megaspin_available=megaspins.megaspin_available,
    )

    if not result["success"]:
        event_manager.log(
            EventType.SPIN,
            SpinOutcome.NO_SPINS,
            user_id=request.user_id,
            chat_id=request.chat_id,
            multiplier=request.multiplier,
        )
        return SlotSpinResponse(
            success=False,
            message=result["message"],
            spins_remaining=result["spins_remaining"],
            megaspin=megaspin_info,
            is_win=False,
        )

    # Telemetry: card/aspect wins are logged in the background task after
    # generation; claim/loss events are logged here so we always emit one
    # SPIN event per bet.
    win_type = result["win_type"]
    if win_type == "claim":
        event_manager.log(
            EventType.SPIN,
            SpinOutcome.CLAIM_WIN,
            user_id=request.user_id,
            chat_id=request.chat_id,
            multiplier=request.multiplier,
        )
    elif win_type is None:
        event_manager.log(
            EventType.SPIN,
            SpinOutcome.LOSS,
            user_id=request.user_id,
            chat_id=request.chat_id,
            multiplier=request.multiplier,
        )

    return SlotSpinResponse(
        success=True,
        spins_remaining=result["spins_remaining"],
        megaspin=megaspin_info,
        is_win=result["is_win"],
        slot_results=[SlotSymbolInfo(**s) for s in result["slot_results"]],
        rarity=result["rarity"],
        win_type=win_type,
        set_id=result["set_id"],
        set_name=result["set_name"],
        spin_result_id=result["spin_result_id"],
        winning_symbol=(
            SlotSymbolSummary(**result["winning_symbol"])
            if result["winning_symbol"]
            else None
        ),
    )


@router.post("/megaspin", response_model=SlotSpinResponse)
async def megaspin(
    request: SpinsRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Atomic megaspin — consume + roll + persist victory token in one call.

    Replaces the previous ``POST /slots/megaspin`` (consume) +
    ``POST /slots/megaspin/verify`` (compute) pair. The merged endpoint:

      * Atomically consumes the megaspin (no-op if unavailable).
      * Derives the slot symbol pool server-side (no client-supplied
        symbols — closes the prior client-trust gap).
      * Picks a guaranteed-win symbol uniformly from cards + sets (no
        claim points), pre-picks a rarity from the "slots" source.
      * Persists a ``SpinResult`` row whose id is returned to the client
        and later required by ``POST /slots/victory``.
      * Returns the full winning symbol payload (incl. b64 icon) so the
        client renders correctly even if its cached symbol pool is stale.
    """
    await verify_user_match(request.user_id, validated_user)
    await validate_user_in_chat(request.user_id, request.chat_id)

    try:
        result = await asyncio.to_thread(
            spin_manager.consume_megaspin_and_roll,
            request.user_id,
            request.chat_id,
            DEBUG_MODE,
        )
    except Exception as e:
        logger.error(
            "Error executing /slots/megaspin for user %s in chat %s: %s",
            request.user_id,
            request.chat_id,
            e,
            exc_info=True,
        )
        event_manager.log(
            EventType.MEGASPIN,
            MegaspinOutcome.ERROR,
            user_id=request.user_id,
            chat_id=request.chat_id,
            error_message=str(e),
        )
        raise HTTPException(status_code=500, detail="Failed to megaspin")

    megaspins = result["megaspin"]
    total_required = spin_repo._get_spins_for_megaspin()
    megaspin_info = MegaspinInfo(
        spins_until_megaspin=megaspins.spins_until_megaspin,
        total_spins_required=total_required,
        megaspin_available=megaspins.megaspin_available,
    )

    if not result["success"]:
        # No megaspin available — log telemetry and short-circuit.
        event_manager.log(
            EventType.MEGASPIN,
            MegaspinOutcome.UNAVAILABLE,
            user_id=request.user_id,
            chat_id=request.chat_id,
        )
        return SlotSpinResponse(
            success=False,
            message=result["message"],
            spins_remaining=result["spins_remaining"] or 0,
            megaspin=megaspin_info,
            is_win=False,
        )

    # Megaspin win event is logged in the background generation task once
    # the card/aspect is actually produced (matches regular spin telemetry).
    return SlotSpinResponse(
        success=True,
        spins_remaining=result["spins_remaining"] or 0,
        megaspin=megaspin_info,
        is_win=result["is_win"],
        slot_results=[SlotSymbolInfo(**s) for s in result["slot_results"]],
        rarity=result["rarity"],
        win_type=result["win_type"],
        set_id=result["set_id"],
        set_name=result["set_name"],
        spin_result_id=result["spin_result_id"],
        winning_symbol=(
            SlotSymbolSummary(**result["winning_symbol"])
            if result["winning_symbol"]
            else None
        ),
    )


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


@router.post("/victory", response_model=SlotsVictoryResponse)
async def slots_victory(
    request: SlotsVictoryRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Redeem a server-issued slot victory token and dispatch processing.

    The client never supplies win details — the canonical outcome was
    stored at spin time in Redis (``spin_result:{id}`` with 10-min TTL).
    We atomically redeem the token via ``GETDEL`` (single-use) and
    dispatch to the matching background generation task using only
    server-trusted fields.
    """
    await verify_user_match(request.user_id, validated_user)

    user_data: Dict[str, Any] = validated_user["user"] or {}
    auth_user_id = user_data.get("id")

    username = user_data.get("username")
    if not username:
        username = await asyncio.to_thread(user_repo.get_username_for_user_id, auth_user_id)
    if not username:
        raise HTTPException(status_code=400, detail="Username not found for user")

    chat_id = str(request.chat_id).strip()
    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id is required")

    if not TELEGRAM_TOKEN:
        raise HTTPException(status_code=503, detail="Bot service unavailable")

    await validate_user_in_chat(request.user_id, chat_id)

    spin_result = await asyncio.to_thread(
        spin_result_repo.redeem,
        request.spin_result_id,
        request.user_id,
        chat_id,
    )
    if not spin_result:
        raise HTTPException(
            status_code=404,
            detail="Spin result not found, already redeemed, or expired",
        )

    normalized_rarity = normalize_rarity(spin_result.rarity) if spin_result.rarity else None
    if spin_result.win_type in ("card", "aspect") and not normalized_rarity:
        # Defensive — should never happen since we persist normalized rarity.
        raise HTTPException(status_code=500, detail="Stored rarity is invalid")

    if spin_result.win_type == "card":
        if not spin_result.display_name or not spin_result.source_type or spin_result.source_id is None:
            raise HTTPException(status_code=500, detail="Stored card victory is incomplete")
        asyncio.create_task(
            process_slots_victory_background(
                bot_token=TELEGRAM_TOKEN,
                debug_mode=DEBUG_MODE,
                username=username,
                normalized_rarity=normalized_rarity,
                display_name=spin_result.display_name,
                chat_id=chat_id,
                source_type=spin_result.source_type,
                source_id=spin_result.source_id,
                user_id=request.user_id,
                gemini_util_instance=gemini_util,
                is_megaspin=spin_result.is_megaspin,
            )
        )
        return SlotsVictoryResponse(status="processing", message="Card generation started")

    if spin_result.win_type == "aspect":
        if spin_result.set_id is None:
            raise HTTPException(status_code=500, detail="Stored aspect victory is incomplete")
        asyncio.create_task(
            process_slot_aspect_victory_background(
                bot_token=TELEGRAM_TOKEN,
                debug_mode=DEBUG_MODE,
                username=username,
                normalized_rarity=normalized_rarity,
                chat_id=chat_id,
                user_id=request.user_id,
                gemini_util_instance=gemini_util,
                set_id=spin_result.set_id,
                is_megaspin=spin_result.is_megaspin,
            )
        )
        return SlotsVictoryResponse(status="processing", message="Aspect generation started")

    raise HTTPException(
        status_code=400,
        detail=f"Stored win_type '{spin_result.win_type}' is not dispatchable",
    )


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
