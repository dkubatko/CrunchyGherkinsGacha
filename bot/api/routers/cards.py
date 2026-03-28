"""
Card-related API endpoints.

This module contains all endpoints for card operations including:
- Getting all cards or user collections
- Card detail retrieval
- Card sharing
- Card image retrieval
- Card locking/unlocking
"""

import asyncio
import logging
import urllib.parse
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from telegram.constants import ParseMode

from api.config import (
    create_bot_instance,
    DEBUG_MODE,
    MINIAPP_URL,
    TELEGRAM_TOKEN,
)
from api.dependencies import (
    get_validated_user,
    validate_chat_exists,
    validate_user_in_chat,
    verify_user_match,
)
from api.schemas import (
    CardImageResponse,
    CardImagesRequest,
    CardLockRequest,
    CardLockResponse,
    ShareCardRequest,
    UserCollectionResponse,
    UserSummary,
)
from settings.constants import get_lock_cost
from utils.miniapp import encode_single_card_token
from utils.schemas import Card as APICard
from repos import card_repo
from repos import claim_repo
from repos import thread_repo
from repos import user_repo
from managers import event_manager
from utils.events import EventType, LockOutcome
from utils.download_token import validate_download_token

# Import limiter for rate limiting
from api.limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cards", tags=["cards"])


@router.get("/all", response_model=List[APICard])
async def get_all_cards_endpoint(
    chat_id: Optional[str] = Query(None, alias="chat_id"),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get all cards that have been claimed."""
    if chat_id:
        await validate_chat_exists(chat_id)
    card_models = await asyncio.to_thread(card_repo.get_all_cards, chat_id)
    return card_models


@router.get("/{user_id}", response_model=UserCollectionResponse)
async def get_user_collection(
    user_id: int,
    chat_id: Optional[str] = Query(None, alias="chat_id"),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get all cards owned by a user.

    This endpoint requires authentication via Authorization header with Telegram WebApp initData.
    """
    if chat_id:
        await validate_chat_exists(chat_id)
    cards = await asyncio.to_thread(card_repo.get_user_collection, user_id, chat_id)
    user_record = await asyncio.to_thread(user_repo.get_user, user_id)
    username = user_record.username if user_record else None
    display_name = user_record.display_name if user_record else None

    if not username:
        username = await asyncio.to_thread(user_repo.get_username_for_user_id, user_id)

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
    """Fetch metadata for a single card, including equipped aspects."""
    card = await asyncio.to_thread(card_repo.get_card_with_aspects, card_id)
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

    card = await asyncio.to_thread(card_repo.get_card, request.card_id)
    if not card:
        logger.warning("Share requested for non-existent card_id: %s", request.card_id)
        raise HTTPException(status_code=404, detail="Card not found")

    card_chat_id = card.chat_id
    if not card_chat_id:
        logger.error("Card %s missing chat_id; cannot share", request.card_id)
        raise HTTPException(status_code=500, detail="Card chat not configured")

    username = user_data.get("username")
    if not username:
        username = await asyncio.to_thread(user_repo.get_username_for_user_id, auth_user_id)

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
        thread_id = await asyncio.to_thread(thread_repo.get_thread_id, card_chat_id)

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


# =============================================================================
# CARD IMAGE ENDPOINTS
# =============================================================================


@router.get("/image/{card_id}", response_model=str)
async def get_card_image_route(
    card_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get the base64 encoded image for a card."""
    image_b64 = await asyncio.to_thread(card_repo.get_card_image, card_id)
    if not image_b64:
        raise HTTPException(status_code=404, detail="Image not found")
    return image_b64


@router.get("/thumbnail/{card_id}", response_model=str)
async def get_card_thumbnail_route(
    card_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get the thumbnail (1/4 scale) base64 encoded image for a card.

    Returns a much smaller image suitable for grid/card views.
    Generates and caches the thumbnail on first request if not yet available.
    """
    thumb_b64 = await asyncio.to_thread(card_repo.get_card_thumbnail, card_id)
    if not thumb_b64:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return thumb_b64


@router.get("/view/{card_id}.png")
@limiter.limit("5/minute")
async def view_card_image_route(
    request: Request,
    card_id: int,
    token: Optional[str] = Query(None, description="Short-lived download token"),
):
    """View the card image directly as PNG.

    This endpoint serves the raw image for viewing/saving in external browsers.
    Requires a short-lived signed token obtained from POST /downloads/token/card/{card_id}.
    Rate limited to 5 requests per minute.
    """
    import base64
    from fastapi.responses import Response

    # Validate token
    if not token:
        raise HTTPException(status_code=401, detail="Download token required")

    if not validate_download_token(token, card_id, TELEGRAM_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    image_b64 = await asyncio.to_thread(card_repo.get_card_image, card_id)
    if not image_b64:
        raise HTTPException(status_code=404, detail="Image not found")

    image_bytes = base64.b64decode(image_b64)

    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=300",
        },
    )


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

    images = await asyncio.to_thread(card_repo.get_card_images_batch, unique_card_ids)

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


# =============================================================================
# CARD LOCK ENDPOINT
# =============================================================================


@router.post("/{card_id}/lock", response_model=CardLockResponse)
async def lock_card(
    card_id: int,
    request: CardLockRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Lock or unlock a card. Locking consumes claim points; unlocking is free."""
    await verify_user_match(request.user_id, validated_user)

    user_data: Dict[str, Any] = validated_user.get("user") or {}
    auth_user_id = user_data.get("id")

    # Fetch the card
    card = await asyncio.to_thread(card_repo.get_card, card_id)
    if not card:
        logger.warning("Lock requested for non-existent card_id: %s", card_id)
        raise HTTPException(status_code=404, detail="Card not found")

    # Verify ownership
    if card.user_id != auth_user_id:
        logger.warning(
            "User %s attempted to lock card %s owned by user %s",
            auth_user_id,
            card_id,
            card.user_id,
        )
        raise HTTPException(status_code=403, detail="You do not own this card")

    # Verify user is enrolled in the chat
    chat_id = str(request.chat_id)
    await validate_user_in_chat(auth_user_id, chat_id)

    # Validate desired state
    if request.lock and card.locked:
        raise HTTPException(status_code=400, detail="Card is already locked")
    if not request.lock and not card.locked:
        raise HTTPException(status_code=400, detail="Card is not locked")

    lock_cost = get_lock_cost(card.rarity)

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
    success = await asyncio.to_thread(card_repo.set_card_locked, card_id, request.lock)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to update card lock status")

    # Get balance for response
    balance = await asyncio.to_thread(claim_repo.get_claim_balance, auth_user_id, chat_id)

    action = "locked" if request.lock else "unlocked"
    logger.info("User %s %s card %s", auth_user_id, action, card_id)

    event_manager.log(
        EventType.LOCK,
        LockOutcome.LOCKED if request.lock else LockOutcome.UNLOCKED,
        user_id=auth_user_id,
        chat_id=chat_id,
        card_id=card_id,
        cost=lock_cost if request.lock else 0,
        via="miniapp",
    )

    return CardLockResponse(
        success=True,
        locked=request.lock,
        balance=balance,
        message=f"Card {action} successfully",
        lock_cost=lock_cost,
    )
