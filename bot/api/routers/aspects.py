"""
Aspect-related API endpoints.

This module contains endpoints for aspect operations including:
- Burning aspects for spins
- Locking/unlocking aspects
"""

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import (
    get_validated_user,
    validate_user_in_chat,
    verify_user_match,
)
from api.schemas import (
    AspectBurnRequest,
    AspectBurnResponse,
    AspectLockRequest,
    AspectLockResponse,
)
from settings.constants import get_lock_cost, get_spin_reward
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
