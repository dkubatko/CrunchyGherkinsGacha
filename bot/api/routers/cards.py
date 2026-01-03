"""
Card-related API endpoints.

This module contains all endpoints for card operations including:
- Getting card configuration (burn rewards, lock costs)
- Getting all cards or user collections
- Card detail retrieval
- Card sharing, locking, and burning
- Card image retrieval
"""

import asyncio
import logging
import urllib.parse
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from telegram.constants import ParseMode

from api.background_tasks import process_burn_notification
from api.config import (
    create_bot_instance,
    DEBUG_MODE,
    MINIAPP_URL,
    TELEGRAM_TOKEN,
)
from api.dependencies import get_validated_user, verify_user_match
from api.schemas import (
    BurnCardRequest,
    BurnCardResponse,
    CardConfigResponse,
    CardImageResponse,
    CardImagesRequest,
    LockCardRequest,
    LockCardResponse,
    ShareCardRequest,
    UserCollectionResponse,
    UserSummary,
)
from settings.constants import RARITIES, get_lock_cost, get_spin_reward
from utils.miniapp import encode_single_card_token
from utils.schemas import Card as APICard
from utils.services import (
    card_service,
    claim_service,
    event_service,
    spin_service,
    thread_service,
    user_service,
)
from utils.events import EventType, BurnOutcome, LockOutcome

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("/config", response_model=CardConfigResponse)
async def get_card_config(
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Expose burn rewards and lock costs for cards."""
    burn_rewards: Dict[str, int] = {}
    lock_costs: Dict[str, int] = {}

    for rarity_name, rarity_details in RARITIES.items():
        if not isinstance(rarity_details, dict):
            continue

        burn_rewards[rarity_name] = get_spin_reward(rarity_name)
        lock_costs[rarity_name] = get_lock_cost(rarity_name)

    return CardConfigResponse(burn_rewards=burn_rewards, lock_costs=lock_costs)


@router.get("/all", response_model=List[APICard])
async def get_all_cards_endpoint(
    chat_id: Optional[str] = Query(None, alias="chat_id"),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get all cards that have been claimed."""
    cards = await asyncio.to_thread(card_service.get_all_cards, chat_id)
    return cards


@router.get("/{user_id}", response_model=UserCollectionResponse)
async def get_user_collection(
    user_id: int,
    chat_id: Optional[str] = Query(None, alias="chat_id"),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get all cards owned by a user.

    This endpoint requires authentication via Authorization header with Telegram WebApp initData.
    """
    cards = await asyncio.to_thread(card_service.get_user_collection, user_id, chat_id)
    user_record = await asyncio.to_thread(user_service.get_user, user_id)
    username = user_record.username if user_record else None
    display_name = user_record.display_name if user_record else None

    if not username:
        username = await asyncio.to_thread(user_service.get_username_for_user_id, user_id)

    if not cards and username is None:
        logger.warning(f"No user or cards found for user_id: {user_id}")
        raise HTTPException(status_code=404, detail="User not found")

    return UserCollectionResponse(
        user=UserSummary(
            user_id=user_id,
            username=username,
            display_name=display_name,
        ),
        cards=cards,
    )


@router.get("/detail/{card_id}", response_model=APICard)
async def get_card_detail(
    card_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Fetch metadata for a single card."""
    card = await asyncio.to_thread(card_service.get_card, card_id)
    if not card:
        logger.warning("Card detail requested for non-existent card_id: %s", card_id)
        raise HTTPException(status_code=404, detail="Card not found")

    return card


@router.post("/share")
async def share_card(
    request: ShareCardRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Share a card to its chat via the Telegram bot."""
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(request.user_id, validated_user)

    # Extract user data from validated data
    user_data: Dict[str, Any] = validated_user["user"] or {}
    auth_user_id = user_data.get("id")

    card = await asyncio.to_thread(card_service.get_card, request.card_id)
    if not card:
        logger.warning("Share requested for non-existent card_id: %s", request.card_id)
        raise HTTPException(status_code=404, detail="Card not found")

    card_chat_id = card.chat_id
    if not card_chat_id:
        logger.error("Card %s missing chat_id; cannot share", request.card_id)
        raise HTTPException(status_code=500, detail="Card chat not configured")

    username = user_data.get("username")
    if not username:
        username = await asyncio.to_thread(user_service.get_username_for_user_id, auth_user_id)

    if not username:
        logger.warning("Unable to resolve username for user_id %s during share", auth_user_id)
        raise HTTPException(status_code=400, detail="Username not found for user")

    card_title = card.title(include_id=True, include_rarity=True)
    if not MINIAPP_URL:
        logger.error("MINIAPP_URL not configured; cannot generate share link")
        raise HTTPException(status_code=500, detail="Mini app URL not configured")

    try:
        from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

        share_token = encode_single_card_token(request.card_id)
        share_url = MINIAPP_URL
        if "?" in MINIAPP_URL:
            separator = "&"
        else:
            separator = "?"
        share_url = f"{MINIAPP_URL}{separator}startapp={urllib.parse.quote(share_token)}"

        bot = create_bot_instance()
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("View here", url=share_url)]])

        set_name = (card.set_name or "Unknown").title()
        message = f"@{username} shared card:\n\n<b>{card_title}</b>\nSet: <b>{set_name}</b>"

        # Add ownership info if the sharer is not the owner
        if card.owner and card.owner != username:
            message += f"\n\n<i>Owned by @{card.owner}</i>"

        # Get thread_id if available
        thread_id = await asyncio.to_thread(thread_service.get_thread_id, card_chat_id)

        send_params = {
            "chat_id": card_chat_id,
            "text": message,
            "reply_markup": keyboard,
            "parse_mode": ParseMode.HTML,
        }
        if thread_id is not None:
            send_params["message_thread_id"] = thread_id

        await bot.send_message(**send_params)

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to share card %s: %s", request.card_id, e)
        raise HTTPException(status_code=500, detail="Failed to share card")


@router.post("/lock", response_model=LockCardResponse)
async def lock_card(
    request: LockCardRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Lock or unlock a card owned by the user.

    Locking consumes the rarity-specific claim point cost. Unlocking does not refund points.
    """
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(request.user_id, validated_user)

    # Extract user data from validated data
    user_data: Dict[str, Any] = validated_user["user"] or {}
    auth_user_id = user_data.get("id")

    # Get the card from database
    card = await asyncio.to_thread(card_service.get_card, request.card_id)
    if not card:
        logger.warning("Lock requested for non-existent card_id: %s", request.card_id)
        raise HTTPException(status_code=404, detail="Card not found")

    # Verify ownership
    username = user_data.get("username")
    if not username:
        username = await asyncio.to_thread(user_service.get_username_for_user_id, auth_user_id)

    if not username:
        logger.warning("Unable to resolve username for user_id %s during lock", auth_user_id)
        raise HTTPException(status_code=400, detail="Username not found for user")

    if card.owner != username:
        logger.warning(
            "User %s (%s) attempted to lock card %s owned by %s",
            username,
            auth_user_id,
            request.card_id,
            card.owner,
        )
        raise HTTPException(status_code=403, detail="You do not own this card")

    # Verify user is enrolled in the chat
    chat_id = str(request.chat_id)
    is_member = await asyncio.to_thread(user_service.is_user_in_chat, chat_id, auth_user_id)
    if not is_member:
        logger.warning("User %s not enrolled in chat %s", auth_user_id, chat_id)
        raise HTTPException(status_code=403, detail="User not enrolled in this chat")

    lock_cost = get_lock_cost(card.rarity)

    # Check current lock status
    if request.lock:
        # User wants to lock the card
        if card.locked:
            raise HTTPException(status_code=400, detail="Card is already locked")

        # Check if user has enough claim points
        current_balance = await asyncio.to_thread(
            claim_service.get_claim_balance, auth_user_id, chat_id
        )

        if current_balance < lock_cost:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Not enough claim points.\n\n" f"Cost: {lock_cost}\nBalance: {current_balance}"
                ),
            )

        # Consume claim points based on rarity
        remaining_balance = await asyncio.to_thread(
            claim_service.reduce_claim_points, auth_user_id, chat_id, lock_cost
        )

        if remaining_balance is None:
            # This shouldn't happen since we checked above, but handle it anyway
            current_balance = await asyncio.to_thread(
                claim_service.get_claim_balance, auth_user_id, chat_id
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    "Not enough claim points.\n\n" f"Cost: {lock_cost}\nBalance: {current_balance}"
                ),
            )

        # Lock the card
        await asyncio.to_thread(card_service.set_card_locked, request.card_id, True)

        logger.info(
            "User %s locked card %s. Remaining balance: %s",
            username,
            request.card_id,
            remaining_balance,
        )

        # Log successful lock event
        event_service.log(
            EventType.LOCK,
            LockOutcome.LOCKED,
            user_id=auth_user_id,
            chat_id=chat_id,
            card_id=request.card_id,
            cost=lock_cost,
            via="miniapp",
        )

        return LockCardResponse(
            success=True,
            locked=True,
            balance=remaining_balance,
            message="Card locked successfully",
            lock_cost=lock_cost,
        )
    else:
        # User wants to unlock the card
        if not card.locked:
            raise HTTPException(status_code=400, detail="Card is not locked")

        # Unlock the card (no refund)
        await asyncio.to_thread(card_service.set_card_locked, request.card_id, False)

        # Get current balance for response
        current_balance = await asyncio.to_thread(
            claim_service.get_claim_balance, auth_user_id, chat_id
        )

        logger.info("User %s unlocked card %s", username, request.card_id)

        # Log successful unlock event
        event_service.log(
            EventType.LOCK,
            LockOutcome.UNLOCKED,
            user_id=auth_user_id,
            chat_id=chat_id,
            card_id=request.card_id,
            via="miniapp",
        )

        return LockCardResponse(
            success=True,
            locked=False,
            balance=current_balance,
            message="Card unlocked successfully.",
            lock_cost=lock_cost,
        )


@router.post("/burn", response_model=BurnCardResponse)
async def burn_card(
    request: BurnCardRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Burn a card owned by the user, removing ownership and awarding spins based on rarity."""
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(request.user_id, validated_user)

    # Extract user data from validated data
    user_data: Dict[str, Any] = validated_user.get("user") or {}
    auth_user_id = user_data.get("id")

    # Get the card from database
    card = await asyncio.to_thread(card_service.get_card, request.card_id)
    if not card:
        logger.warning("Burn requested for non-existent card_id: %s", request.card_id)
        raise HTTPException(status_code=404, detail="Card not found")

    # Verify ownership
    username = user_data.get("username")
    if not username:
        username = await asyncio.to_thread(user_service.get_username_for_user_id, auth_user_id)

    if not username:
        logger.warning("Unable to resolve username for user_id %s during burn", auth_user_id)
        raise HTTPException(status_code=400, detail="Username not found for user")

    if card.owner != username:
        logger.warning(
            "User %s (%s) attempted to burn card %s owned by %s",
            username,
            auth_user_id,
            request.card_id,
            card.owner,
        )
        raise HTTPException(status_code=403, detail="You do not own this card")

    # Verify card is associated with the specified chat
    if card.chat_id != str(request.chat_id):
        logger.warning(
            "Card %s chat_id mismatch. Card chat: %s, Request chat: %s",
            request.card_id,
            card.chat_id,
            request.chat_id,
        )
        raise HTTPException(status_code=400, detail="Card is not associated with this chat")

    # Verify user is enrolled in the chat
    chat_id = str(request.chat_id)
    is_member = await asyncio.to_thread(user_service.is_user_in_chat, chat_id, auth_user_id)
    if not is_member:
        logger.warning("User %s not enrolled in chat %s", auth_user_id, chat_id)
        raise HTTPException(status_code=403, detail="User not enrolled in this chat")

    # Get spin reward for the card's rarity
    spin_reward = get_spin_reward(card.rarity)
    if spin_reward <= 0:
        logger.error("No spin reward configured for rarity %s", card.rarity)
        raise HTTPException(status_code=500, detail="No spin reward configured for this rarity")

    # Delete the card from the database
    success = await asyncio.to_thread(card_service.delete_card, request.card_id)

    if not success:
        logger.error("Failed to delete card %s", request.card_id)
        raise HTTPException(status_code=500, detail="Failed to burn card")

    # Award spins to the user
    new_spin_total = await asyncio.to_thread(
        spin_service.increment_user_spins, auth_user_id, chat_id, spin_reward
    )

    if new_spin_total is None:
        logger.error(
            "Failed to award spins to user %s in chat %s after burning card %s",
            auth_user_id,
            chat_id,
            request.card_id,
        )
        # Card is already burned, but spins weren't awarded - this is a critical error
        raise HTTPException(status_code=500, detail="Card burned but failed to award spins")

    logger.info(
        "Card %s (%s %s %s) burned by user %s (%s) in chat %s. Awarded %s spins. New total: %s",
        request.card_id,
        card.rarity,
        card.modifier,
        card.base_name,
        username,
        auth_user_id,
        chat_id,
        spin_reward,
        new_spin_total,
    )

    # Log successful burn event
    event_service.log(
        EventType.BURN,
        BurnOutcome.SUCCESS,
        user_id=auth_user_id,
        chat_id=chat_id,
        card_id=request.card_id,
        rarity=card.rarity,
        spin_reward=spin_reward,
        new_spin_total=new_spin_total,
    )

    # Store card details before returning response
    card_display_name = card.title()
    card_rarity = card.rarity

    # Spawn background task to send notification to chat
    asyncio.create_task(
        process_burn_notification(
            bot_token=TELEGRAM_TOKEN,
            debug_mode=DEBUG_MODE,
            username=username,
            card_rarity=card_rarity,
            card_display_name=card_display_name,
            spin_amount=spin_reward,
            chat_id=chat_id,
        )
    )

    return BurnCardResponse(
        success=True,
        message=f"Card burned successfully! Awarded {spin_reward} spins.",
        spins_awarded=spin_reward,
        new_spin_total=new_spin_total,
    )


# =============================================================================
# CARD IMAGE ENDPOINTS
# =============================================================================


@router.get("/image/{card_id}", response_model=str)
async def get_card_image_route(
    card_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get the base64 encoded image for a card."""
    image_b64 = await asyncio.to_thread(card_service.get_card_image, card_id)
    if not image_b64:
        raise HTTPException(status_code=404, detail="Image not found")
    return image_b64


@router.post("/images", response_model=List[CardImageResponse])
async def get_card_images_route(
    request: CardImagesRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get base64 encoded images for multiple cards in a single batch."""
    card_ids = request.card_ids or []
    unique_card_ids = list(dict.fromkeys(card_ids))

    if not unique_card_ids:
        raise HTTPException(status_code=400, detail="card_ids must contain at least one value")

    if len(unique_card_ids) > 3:
        raise HTTPException(
            status_code=400, detail="A maximum of 3 card IDs can be requested per batch"
        )

    images = await asyncio.to_thread(card_service.get_card_images_batch, unique_card_ids)

    if not images:
        raise HTTPException(status_code=404, detail="No images found for requested card IDs")

    response_payload = [
        CardImageResponse(card_id=card_id, image_b64=image)
        for card_id, image in images.items()
        if image
    ]

    if not response_payload:
        raise HTTPException(status_code=404, detail="No images found for requested card IDs")

    return response_payload
