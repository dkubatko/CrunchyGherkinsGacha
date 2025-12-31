"""
Trade-related API endpoints.

This module contains all endpoints for card trading operations.
"""

import asyncio
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from api.config import create_bot_instance, MINIAPP_URL, TELEGRAM_TOKEN
from api.dependencies import get_validated_user
from api.helpers import build_single_card_url
from settings.constants import TRADE_REQUEST_MESSAGE
from utils.schemas import Card as APICard
from utils.services import card_service, thread_service, event_service
from utils.events import EventType, TradeOutcome

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trade", tags=["trade"])


@router.get("/{card_id}/options", response_model=List[APICard])
async def get_trade_options(
    card_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get trade options for a specific card, scoped to the same chat."""
    card = await asyncio.to_thread(card_service.get_card, card_id)
    if not card:
        logger.warning(f"Requested trade options for non-existent card_id: {card_id}")
        raise HTTPException(status_code=404, detail="Card not found")

    if not card.chat_id:
        logger.warning(f"Card {card_id} has no chat_id; cannot load trade options")
        raise HTTPException(status_code=400, detail="Card is not associated with a chat")

    cards = await asyncio.to_thread(card_service.get_all_cards, card.chat_id)

    initiating_owner = card.owner
    filtered_cards = [
        card_option
        for card_option in cards
        if card_option.id != card_id
        and card_option.owner is not None
        and card_option.owner != initiating_owner
    ]
    return filtered_cards


@router.post("/{card_id1}/{card_id2}")
async def execute_trade(
    card_id1: int,
    card_id2: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Execute a card trade between two cards."""
    # Get user data from validated init data
    user_data = validated_user["user"]
    user_id = user_data.get("id")

    if not user_id:
        logger.warning(f"Missing user_id in init data for trade {card_id1}/{card_id2}")
        raise HTTPException(status_code=400, detail="Invalid user data in init data")

    # Check if bot token is available
    if not TELEGRAM_TOKEN:
        logger.error("Bot token not available for trade execution")
        raise HTTPException(status_code=503, detail="Bot service unavailable")

    try:
        # Get cards from database
        card1 = await asyncio.to_thread(card_service.get_card, card_id1)
        card2 = await asyncio.to_thread(card_service.get_card, card_id2)

        if not card1 or not card2:
            raise HTTPException(status_code=404, detail="One or both card IDs are invalid")

        card1_chat_id = card1.chat_id
        card2_chat_id = card2.chat_id

        if not card1_chat_id or not card2_chat_id:
            logger.error(
                "Missing chat_id on cards %s and %s",
                card_id1,
                card_id2,
            )
            raise HTTPException(status_code=500, detail="Card chat not configured")

        if card1_chat_id != card2_chat_id:
            logger.warning(
                "Trade attempted between cards %s and %s from different chats (%s vs %s)",
                card_id1,
                card_id2,
                card1_chat_id,
                card2_chat_id,
            )
            raise HTTPException(
                status_code=400,
                detail="Both cards must belong to the same chat to trade",
            )
        chat_id = card1_chat_id  # Get current user's username from the validated init data
        current_username = user_data.get("username")
        if not current_username:
            logger.error(f"Username not found in init data for user_id {user_id}")
            raise HTTPException(status_code=400, detail="Username not found in init data")

        # Validate trade
        if card1.owner != current_username:
            raise HTTPException(status_code=403, detail=f"You do not own card {card1.title()}")

        if card2.owner == current_username:
            raise HTTPException(status_code=400, detail=f"You already own card {card2.title()}")

        # Send trade request message with accept/reject buttons
        trade_message = TRADE_REQUEST_MESSAGE.format(
            user1_username=current_username,
            card1_title=card1.title(include_rarity=True),
            user2_username=card2.owner,
            card2_title=card2.title(include_rarity=True),
        )

        # Create inline keyboard with accept/reject buttons, card view links, and cancel button
        keyboard = [
            [
                InlineKeyboardButton("Accept", callback_data=f"trade_accept_{card_id1}_{card_id2}"),
                InlineKeyboardButton("Reject", callback_data=f"trade_reject_{card_id1}_{card_id2}"),
            ]
        ]

        # Add card view links
        if MINIAPP_URL:
            card1_url = build_single_card_url(card_id1)
            card2_url = build_single_card_url(card_id2)
            keyboard.append(
                [
                    InlineKeyboardButton("Card 1", url=card1_url),
                    InlineKeyboardButton("Card 2", url=card2_url),
                ]
            )

        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            # Create a new bot instance to avoid event loop conflicts
            bot = create_bot_instance()

            # Get thread_id for trade notifications, fallback to main if trade not set
            thread_id = await asyncio.to_thread(thread_service.get_thread_id, str(chat_id), "trade")
            if thread_id is None:
                thread_id = await asyncio.to_thread(
                    thread_service.get_thread_id, str(chat_id), "main"
                )

            send_params = {
                "chat_id": chat_id,
                "text": trade_message,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
            }
            if thread_id is not None:
                send_params["message_thread_id"] = thread_id

            # Send message using the new bot instance
            await bot.send_message(**send_params)

            # Log trade created event
            event_service.log(
                EventType.TRADE,
                TradeOutcome.CREATED,
                user_id=user_id,
                chat_id=str(chat_id),
                card_id=card_id1,
                target_card_id=card_id2,
                target_user=card2.owner,
                source="miniapp",
            )
        except Exception as e:
            logger.error(f"Failed to send trade request message to chat {chat_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to send trade request")

        return {"success": True, "message": "Trade request sent successfully"}

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Unexpected error in trade endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
