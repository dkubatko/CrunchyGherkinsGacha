"""
Download-related API endpoints.

This module contains endpoints for generating download tokens
used to access protected resources like card images.
"""

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from api.config import TELEGRAM_TOKEN
from api.dependencies import get_validated_user
from utils.download_token import create_download_token
from utils.services import card_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/downloads", tags=["downloads"])


@router.post("/token/card/{card_id}")
async def create_card_download_token(
    card_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Generate a short-lived signed token for downloading a card image.

    The token is valid for 5 minutes and can be used multiple times within that window.
    Uses HMAC signatures so no server-side storage is needed.
    """
    # Verify card exists
    card_data = await asyncio.to_thread(card_service.get_card, card_id)
    if not card_data:
        raise HTTPException(status_code=404, detail="Card not found")

    # Generate signed token using the Telegram token as the secret
    token = create_download_token(card_id, TELEGRAM_TOKEN)

    return {"token": token}
