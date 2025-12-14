"""
User-related API endpoints.

This module contains all endpoints for user profile operations.
"""

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_validated_user
from api.schemas import UserProfileResponse
from utils.services import (
    card_service,
    claim_service,
    spin_service,
    user_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/{user_id}/profile", response_model=UserProfileResponse)
async def get_user_profile(
    user_id: int,
    chat_id: str = Query(..., description="Chat ID"),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get the general profile information for a user."""
    try:
        # We don't enforce user_id match here because we might be viewing another user's profile

        # Get user info
        user = await asyncio.to_thread(user_service.get_user, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get claim balance
        claim_balance = await asyncio.to_thread(claim_service.get_claim_balance, user_id, chat_id)

        # Get spin balance (with refresh logic)
        spin_balance = await asyncio.to_thread(
            spin_service.get_or_update_user_spins_with_daily_refresh, user_id, chat_id
        )

        # Get card count
        card_count = await asyncio.to_thread(card_service.get_user_card_count, user_id, chat_id)

        return UserProfileResponse(
            user_id=user.user_id,
            username=user.username,
            display_name=user.display_name,
            profile_imageb64=user.profile_imageb64,
            claim_balance=claim_balance,
            spin_balance=spin_balance,
            card_count=card_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting profile for user {user_id} in chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user profile")
