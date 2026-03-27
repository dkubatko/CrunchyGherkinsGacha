"""
Aspect-related API endpoints.

This module contains endpoints for aspect operations including:
- Listing user aspects
- Aspect detail retrieval
- Aspect image retrieval (full and thumbnail)
- Batch thumbnail retrieval
- Aspect config (burn rewards, lock costs)
- Burning aspects for spins
- Locking/unlocking aspects
"""

import asyncio
import html
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import (
    get_validated_user,
    validate_user_in_chat,
    verify_user_match,
)
from api.config import create_bot_instance
from api.schemas import (
    AspectBurnRequest,
    AspectBurnResponse,
    AspectConfigResponse,
    AspectImageResponse,
    AspectImagesRequest,
    AspectLockRequest,
    AspectLockResponse,
    EquipInitiateRequest,
    EquipInitiateResponse,
)
from settings.constants import EQUIP_CONFIRM_MESSAGE, RARITY_ORDER, get_lock_cost, get_spin_reward
from utils.schemas import Card, OwnedAspect
from repos import aspect_repo
from repos import card_repo
from repos import claim_repo
from repos import equip_session_repo
from repos import spin_repo
from repos import thread_repo
from managers import aspect_manager
from managers import event_manager
from utils.events import EventType, BurnOutcome, LockOutcome

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aspects", tags=["aspects"])


# =============================================================================
# READ ENDPOINTS
# =============================================================================


@router.get("", response_model=List[OwnedAspect])
async def get_user_aspects(
    chat_id: Optional[str] = Query(None, alias="chat_id"),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get all unequipped aspects owned by the authenticated user."""
    user_data: Dict[str, Any] = validated_user.get("user") or {}
    auth_user_id = user_data.get("id")

    aspect_models = await asyncio.to_thread(
        aspect_repo.get_user_aspects,
        auth_user_id,
        chat_id=chat_id,
    )
    return aspect_models


@router.get("/config", response_model=AspectConfigResponse)
async def get_aspect_config(
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get aspect burn rewards and lock costs for each rarity."""
    burn_rewards = {r: get_spin_reward(r) for r in RARITY_ORDER}
    lock_costs = {r: get_lock_cost(r) for r in RARITY_ORDER}
    return AspectConfigResponse(burn_rewards=burn_rewards, lock_costs=lock_costs)


# =============================================================================
# IMAGE ENDPOINTS
# =============================================================================


@router.get("/image/{aspect_id}", response_model=str)
async def get_aspect_image_route(
    aspect_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get the base64 encoded full-size image for an aspect."""
    image_b64 = await asyncio.to_thread(aspect_repo.get_aspect_image, aspect_id)
    if not image_b64:
        raise HTTPException(status_code=404, detail="Image not found")
    return image_b64


@router.get("/thumbnail/{aspect_id}", response_model=str)
async def get_aspect_thumbnail_route(
    aspect_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get the thumbnail (1/4 scale) base64 encoded image for an aspect."""
    thumb_b64 = await asyncio.to_thread(aspect_repo.get_aspect_thumbnail, aspect_id)
    if not thumb_b64:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return thumb_b64


@router.post("/thumbnails", response_model=List[AspectImageResponse])
async def get_aspect_thumbnails_batch(
    request: AspectImagesRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get base64 encoded thumbnails for multiple aspects in a single batch."""
    aspect_ids = request.aspect_ids or []
    unique_ids = list(dict.fromkeys(aspect_ids))

    if not unique_ids:
        raise HTTPException(status_code=400, detail="aspect_ids must contain at least one value")

    if len(unique_ids) > 3:
        raise HTTPException(
            status_code=400, detail="A maximum of 3 aspect IDs can be requested per batch"
        )

    images = await asyncio.to_thread(aspect_repo.get_aspect_images_batch, unique_ids)

    if not images:
        raise HTTPException(status_code=404, detail="No images found for requested aspect IDs")

    response_payload = [
        AspectImageResponse(aspect_id=aid, image_b64=image)
        for aid, image in images.items()
        if image
    ]

    if not response_payload:
        raise HTTPException(status_code=404, detail="No images found for requested aspect IDs")

    return response_payload


# =============================================================================
# EQUIP ENDPOINTS
# =============================================================================


@router.get("/{aspect_id}/eligible-cards", response_model=List[Card])
async def get_eligible_cards(
    aspect_id: int,
    user_id: int = Query(..., alias="user_id"),
    chat_id: str = Query(..., alias="chat_id"),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Return cards eligible for equipping the given aspect.

    Filters:
    - Owned by the authenticated user
    - Same chat_id as the aspect
    - Not locked
    - aspect_count < 5
    - Rarity compatible (card rarity >= aspect rarity, or aspect is Unique)
    """
    await verify_user_match(user_id, validated_user)

    # Fetch the aspect
    aspect = await asyncio.to_thread(aspect_repo.get_aspect_by_id, aspect_id)
    if not aspect:
        raise HTTPException(status_code=404, detail="Aspect not found")

    # Verify ownership
    user_data: Dict[str, Any] = validated_user.get("user") or {}
    auth_user_id = user_data.get("id")
    if aspect.user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="You do not own this aspect")

    # Verify chat association
    if aspect.chat_id != chat_id:
        raise HTTPException(status_code=400, detail="Aspect is not associated with this chat")

    # Fetch user's cards in this chat
    cards = await asyncio.to_thread(
        card_repo.get_user_collection, auth_user_id, chat_id
    )

    # Filter for eligibility
    aspect_rarity_idx = RARITY_ORDER.index(aspect.rarity) if aspect.rarity in RARITY_ORDER else len(RARITY_ORDER)

    eligible = []
    for card in cards:
        # Must not be locked
        if card.locked:
            continue
        # Must have capacity
        if card.aspect_count >= 5:
            continue
        # Rarity check (Unique aspects can go on any card)
        if aspect.rarity != "Unique":
            card_rarity_idx = RARITY_ORDER.index(card.rarity) if card.rarity in RARITY_ORDER else -1
            if aspect_rarity_idx > card_rarity_idx:
                continue
        eligible.append(card)

    return eligible


@router.post("/{aspect_id}/equip-initiate", response_model=EquipInitiateResponse)
async def equip_initiate(
    aspect_id: int,
    request: EquipInitiateRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Initiate an equip from the miniapp.

    Validates all equip preconditions, stores session in DB, and sends
    the equip confirmation message with inline keyboard to the group chat.
    """
    await verify_user_match(request.user_id, validated_user)

    user_data: Dict[str, Any] = validated_user.get("user") or {}
    auth_user_id = user_data.get("id")
    chat_id = str(request.chat_id)

    # Fetch aspect
    aspect = await asyncio.to_thread(aspect_repo.get_aspect_by_id, aspect_id)
    if not aspect:
        raise HTTPException(status_code=404, detail="Aspect not found")

    # Fetch card
    card = await asyncio.to_thread(card_repo.get_card, request.card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    # Ownership checks
    if aspect.user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="You do not own this aspect")
    if card.user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="You do not own this card")

    # Chat match
    if aspect.chat_id != chat_id:
        raise HTTPException(status_code=400, detail="Aspect is not in this chat")
    if not card.chat_id or card.chat_id != chat_id:
        raise HTTPException(status_code=400, detail="Card is not in this chat")

    # Lock checks
    if card.locked:
        raise HTTPException(status_code=400, detail="Cannot equip onto a locked card. Unlock it first.")
    if aspect.locked:
        raise HTTPException(status_code=400, detail="Cannot equip a locked aspect. Unlock it first.")

    # Check if aspect is already equipped
    is_equipped = await asyncio.to_thread(aspect_repo.is_aspect_equipped, aspect_id)
    if is_equipped:
        raise HTTPException(status_code=400, detail="This aspect is already equipped on a card.")

    # Capacity
    if card.aspect_count >= 5:
        raise HTTPException(status_code=400, detail="This card already has 5 aspects equipped (maximum).")

    # Rarity compatibility
    if aspect.rarity != "Unique":
        aspect_idx = RARITY_ORDER.index(aspect.rarity) if aspect.rarity in RARITY_ORDER else len(RARITY_ORDER)
        card_idx = RARITY_ORDER.index(card.rarity) if card.rarity in RARITY_ORDER else -1
        if aspect_idx > card_idx:
            raise HTTPException(
                status_code=400,
                detail=f"Rarity mismatch: a {aspect.rarity} aspect cannot be equipped on a {card.rarity} card.",
            )

    # Validate user in chat
    await validate_user_in_chat(auth_user_id, chat_id)

    # Resolve name prefix
    name_prefix = request.name_prefix or aspect.display_name or "Unknown"
    name_prefix = name_prefix[0].upper() + name_prefix[1:] if name_prefix else name_prefix

    # Validate name
    if len(name_prefix) > 30:
        raise HTTPException(status_code=400, detail="Name prefix is too long. Please keep it under 30 characters.")
    invalid_chars = set("<>&*_`")
    if any(ch in invalid_chars for ch in name_prefix):
        raise HTTPException(status_code=400, detail="Name prefix contains invalid characters.")

    # Build new title
    new_title = f"{name_prefix} {card.base_name}"
    card_title = card.title(include_id=True)

    # Store equip session in DB
    await asyncio.to_thread(
        equip_session_repo.create_or_replace,
        user_id=auth_user_id,
        chat_id=chat_id,
        aspect_id=aspect_id,
        card_id=request.card_id,
        name_prefix=name_prefix,
        aspect_name=aspect.display_name or "Unknown",
        aspect_rarity=aspect.rarity,
        card_title=card_title,
        new_title=new_title,
    )

    # Build confirmation message + inline keyboard
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.constants import ParseMode

    confirm_text = EQUIP_CONFIRM_MESSAGE.format(
        aspect_id=aspect_id,
        aspect_name=html.escape(aspect.display_name or "Unknown"),
        aspect_rarity=aspect.rarity,
        card_id=request.card_id,
        card_title=html.escape(card_title),
        card_rarity=card.rarity,
        new_title=html.escape(new_title),
        aspect_count=card.aspect_count,
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Equip!",
                    callback_data=f"equip_yes_{aspect_id}_{request.card_id}_{auth_user_id}",
                ),
                InlineKeyboardButton(
                    "Cancel",
                    callback_data=f"equip_cancel_{aspect_id}_{request.card_id}_{auth_user_id}",
                ),
            ]
        ]
    )

    # Send to group chat
    try:
        bot = create_bot_instance()
        thread_id = await asyncio.to_thread(thread_repo.get_thread_id, chat_id)

        send_params: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": confirm_text,
            "reply_markup": keyboard,
            "parse_mode": ParseMode.HTML,
        }
        if thread_id is not None:
            send_params["message_thread_id"] = thread_id

        await bot.send_message(**send_params)
    except Exception as exc:
        logger.error("Failed to send equip confirmation to chat %s: %s", chat_id, exc)
        raise HTTPException(status_code=500, detail="Failed to send confirmation to chat")

    return EquipInitiateResponse(
        success=True,
        message="Equip confirmation sent to chat! Head there to confirm.",
    )


# =============================================================================
# DETAIL ENDPOINT (path param catch-all - must come after specific paths)
# =============================================================================


@router.get("/{aspect_id}", response_model=OwnedAspect)
async def get_aspect_detail(
    aspect_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Fetch metadata for a single aspect."""
    aspect = await asyncio.to_thread(aspect_repo.get_aspect_by_id, aspect_id)
    if not aspect:
        logger.warning("Aspect detail requested for non-existent aspect_id: %s", aspect_id)
        raise HTTPException(status_code=404, detail="Aspect not found")
    return aspect


@router.post("/{aspect_id}/burn", response_model=AspectBurnResponse)
async def burn_aspect(
    aspect_id: int,
    request: AspectBurnRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Burn an owned aspect, removing it and awarding spins based on rarity."""
    await verify_user_match(request.user_id, validated_user)

    user_data: Dict[str, Any] = validated_user.get("user") or {}
    auth_user_id = user_data.get("id")

    # Fetch the aspect
    aspect = await asyncio.to_thread(aspect_repo.get_aspect_by_id, aspect_id)
    if not aspect:
        logger.warning("Burn requested for non-existent aspect_id: %s", aspect_id)
        raise HTTPException(status_code=404, detail="Aspect not found")

    # Verify ownership
    if aspect.user_id != auth_user_id:
        logger.warning(
            "User %s attempted to burn aspect %s owned by user %s",
            auth_user_id,
            aspect_id,
            aspect.user_id,
        )
        raise HTTPException(status_code=403, detail="You do not own this aspect")

    # Verify chat association
    chat_id = str(request.chat_id)
    if aspect.chat_id != chat_id:
        logger.warning(
            "Aspect %s chat_id mismatch. Aspect chat: %s, Request chat: %s",
            aspect_id,
            aspect.chat_id,
            chat_id,
        )
        raise HTTPException(status_code=400, detail="Aspect is not associated with this chat")

    # Verify user is enrolled in the chat
    await validate_user_in_chat(auth_user_id, chat_id)

    # Get expected spin reward
    spin_reward = get_spin_reward(aspect.rarity)
    if spin_reward <= 0:
        logger.error("No spin reward configured for rarity %s", aspect.rarity)
        raise HTTPException(status_code=500, detail="No spin reward configured for this rarity")

    # Perform the burn (validates unlocked + unequipped internally)
    reward = await asyncio.to_thread(aspect_manager.burn_aspect, aspect_id, auth_user_id, chat_id)

    if reward is None:
        logger.warning(
            "burn_aspect returned None for aspect %s user %s",
            aspect_id,
            auth_user_id,
        )
        raise HTTPException(
            status_code=400,
            detail="Cannot burn this aspect. It may be locked or equipped.",
        )

    # Get updated spin balance
    spins_record = await asyncio.to_thread(spin_repo.get_user_spins, auth_user_id, chat_id)
    new_spin_total = spins_record.count if spins_record else reward

    logger.info(
        "Aspect %s (%s %s) burned by user %s in chat %s. Awarded %s spins. New total: %s",
        aspect_id,
        aspect.rarity,
        aspect.display_name,
        auth_user_id,
        chat_id,
        reward,
        new_spin_total,
    )

    event_manager.log(
        EventType.BURN,
        BurnOutcome.SUCCESS,
        user_id=auth_user_id,
        chat_id=chat_id,
        aspect_id=aspect_id,
        rarity=aspect.rarity,
        spin_reward=reward,
        new_spin_total=new_spin_total,
    )

    return AspectBurnResponse(
        success=True,
        message=f"Aspect burned successfully! Awarded {reward} spins.",
        spins_awarded=reward,
        new_spin_total=new_spin_total,
    )


@router.post("/{aspect_id}/lock", response_model=AspectLockResponse)
async def lock_aspect(
    aspect_id: int,
    request: AspectLockRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Lock or unlock an owned aspect. Locking consumes claim points."""
    await verify_user_match(request.user_id, validated_user)

    user_data: Dict[str, Any] = validated_user.get("user") or {}
    auth_user_id = user_data.get("id")

    # Fetch the aspect
    aspect = await asyncio.to_thread(aspect_repo.get_aspect_by_id, aspect_id)
    if not aspect:
        logger.warning("Lock requested for non-existent aspect_id: %s", aspect_id)
        raise HTTPException(status_code=404, detail="Aspect not found")

    # Verify ownership
    if aspect.user_id != auth_user_id:
        logger.warning(
            "User %s attempted to lock aspect %s owned by user %s",
            auth_user_id,
            aspect_id,
            aspect.user_id,
        )
        raise HTTPException(status_code=403, detail="You do not own this aspect")

    # Verify user is enrolled in the chat
    chat_id = str(request.chat_id)
    await validate_user_in_chat(auth_user_id, chat_id)

    # Validate desired state
    if request.lock and aspect.locked:
        raise HTTPException(status_code=400, detail="Aspect is already locked")
    if not request.lock and not aspect.locked:
        raise HTTPException(status_code=400, detail="Aspect is not locked")

    lock_cost = get_lock_cost(aspect.rarity)

    if request.lock:
        # Charge claim points for locking
        current_balance = await asyncio.to_thread(
            claim_repo.get_claim_balance, auth_user_id, chat_id
        )
        if current_balance < lock_cost:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Not enough claim points.\n\n" f"Cost: {lock_cost}\nBalance: {current_balance}"
                ),
            )

        remaining_balance = await asyncio.to_thread(
            claim_repo.reduce_claim_points, auth_user_id, chat_id, lock_cost
        )
        if remaining_balance is None:
            current_balance = await asyncio.to_thread(
                claim_repo.get_claim_balance, auth_user_id, chat_id
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    "Not enough claim points.\n\n" f"Cost: {lock_cost}\nBalance: {current_balance}"
                ),
            )

    # Toggle lock
    new_lock_state = await asyncio.to_thread(aspect_repo.lock_aspect, aspect_id, auth_user_id)

    if new_lock_state is None:
        raise HTTPException(status_code=400, detail="Failed to update aspect lock status")

    # Get balance for response
    balance = await asyncio.to_thread(claim_repo.get_claim_balance, auth_user_id, chat_id)

    action = "locked" if new_lock_state else "unlocked"
    logger.info("User %s %s aspect %s", auth_user_id, action, aspect_id)

    event_manager.log(
        EventType.LOCK,
        LockOutcome.LOCKED if new_lock_state else LockOutcome.UNLOCKED,
        user_id=auth_user_id,
        chat_id=chat_id,
        aspect_id=aspect_id,
        cost=lock_cost if new_lock_state else 0,
        via="miniapp",
    )

    return AspectLockResponse(
        success=True,
        locked=new_lock_state,
        balance=balance,
        message=f"Aspect {action} successfully",
        lock_cost=lock_cost,
    )
