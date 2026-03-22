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
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import (
    get_validated_user,
    validate_user_in_chat,
    verify_user_match,
)
from api.schemas import (
    AspectBurnRequest,
    AspectBurnResponse,
    AspectConfigResponse,
    AspectImageResponse,
    AspectImagesRequest,
    AspectLockRequest,
    AspectLockResponse,
)
from settings.constants import RARITY_ORDER, get_lock_cost, get_spin_reward
from utils.schemas import OwnedAspect
from utils.services import (
    aspect_service,
    claim_service,
    event_service,
    spin_service,
    user_service,
)
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

    aspects = await asyncio.to_thread(
        aspect_service.get_user_aspects,
        auth_user_id,
        chat_id=chat_id,
    )
    return aspects


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
    image_b64 = await asyncio.to_thread(aspect_service.get_aspect_image, aspect_id)
    if not image_b64:
        raise HTTPException(status_code=404, detail="Image not found")
    return image_b64


@router.get("/thumbnail/{aspect_id}", response_model=str)
async def get_aspect_thumbnail_route(
    aspect_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get the thumbnail (1/4 scale) base64 encoded image for an aspect."""
    thumb_b64 = await asyncio.to_thread(aspect_service.get_aspect_thumbnail, aspect_id)
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

    images = await asyncio.to_thread(aspect_service.get_aspect_images_batch, unique_ids)

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
# DETAIL ENDPOINT (path param catch-all - must come after specific paths)
# =============================================================================


@router.get("/{aspect_id}", response_model=OwnedAspect)
async def get_aspect_detail(
    aspect_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Fetch metadata for a single aspect."""
    aspect = await asyncio.to_thread(aspect_service.get_aspect_by_id, aspect_id)
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
    aspect = await asyncio.to_thread(aspect_service.get_aspect_by_id, aspect_id)
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
    reward = await asyncio.to_thread(aspect_service.burn_aspect, aspect_id, auth_user_id, chat_id)

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
    spins_record = await asyncio.to_thread(spin_service.get_user_spins, auth_user_id, chat_id)
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

    event_service.log(
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
    aspect = await asyncio.to_thread(aspect_service.get_aspect_by_id, aspect_id)
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
            claim_service.get_claim_balance, auth_user_id, chat_id
        )
        if current_balance < lock_cost:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Not enough claim points.\n\n" f"Cost: {lock_cost}\nBalance: {current_balance}"
                ),
            )

        remaining_balance = await asyncio.to_thread(
            claim_service.reduce_claim_points, auth_user_id, chat_id, lock_cost
        )
        if remaining_balance is None:
            current_balance = await asyncio.to_thread(
                claim_service.get_claim_balance, auth_user_id, chat_id
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    "Not enough claim points.\n\n" f"Cost: {lock_cost}\nBalance: {current_balance}"
                ),
            )

    # Toggle lock
    new_lock_state = await asyncio.to_thread(aspect_service.lock_aspect, aspect_id, auth_user_id)

    if new_lock_state is None:
        raise HTTPException(status_code=400, detail="Failed to update aspect lock status")

    # Get balance for response
    balance = await asyncio.to_thread(claim_service.get_claim_balance, auth_user_id, chat_id)

    action = "locked" if new_lock_state else "unlocked"
    logger.info("User %s %s aspect %s", auth_user_id, action, aspect_id)

    event_service.log(
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
