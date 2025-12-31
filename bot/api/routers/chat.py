"""
Chat-related API endpoints.

This module contains all endpoints for chat operations.
"""

import asyncio
import base64
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_validated_user
from api.schemas import SlotSymbolSummary
from utils.services import user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/{chat_id}/slot-symbols", response_model=List[SlotSymbolSummary])
async def get_slot_symbols_endpoint(
    chat_id: str,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get all slot symbols (users, characters, and claim) for a specific chat with their display names and icons."""
    try:
        # Get users and characters data from database
        data = await asyncio.to_thread(user_service.get_chat_users_and_characters, chat_id)

        # Load claim icon from file
        claim_icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data",
            "slots",
            "claim_icon.png",
        )

        claim_icon_b64: Optional[str] = None
        try:
            with open(claim_icon_path, "rb") as f:
                claim_icon_bytes = f.read()
                claim_icon_b64 = base64.b64encode(claim_icon_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to load claim icon: {e}")
            # Continue without claim icon rather than failing the whole request

        # Add claim point as a special symbol if icon was loaded successfully
        if claim_icon_b64:
            # Use a special ID that won't conflict with user/character IDs (e.g., -1)
            claim_symbol = {
                "id": -1,
                "display_name": "Claim",
                "slot_iconb64": claim_icon_b64,
                "type": "claim",
            }
            data.append(claim_symbol)

        # Convert to response models and return directly
        return [SlotSymbolSummary(**item) for item in data]

    except Exception as e:
        logger.error(f"Error fetching slot symbols for chat_id {chat_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch slot symbols")
