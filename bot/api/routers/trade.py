"""Unified trade API endpoints.

Endpoints:
  GET  /trade/{offer_type}/{offer_id}/options/cards    → tradeable cards
  GET  /trade/{offer_type}/{offer_id}/options/aspects  → tradeable aspects
  POST /trade/{offer_type}/{offer_id}/{want_type}/{want_id}  → execute trade
"""

import asyncio
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from api.config import create_bot_instance, MINIAPP_URL, TELEGRAM_TOKEN
from api.dependencies import get_validated_user
from api.helpers import build_single_card_url, build_single_aspect_url
from settings.constants import TRADE_REQUEST_MESSAGE
from utils.schemas import Card as APICard, OwnedAspect as APIAspect
from repos import card_repo, aspect_repo, thread_repo
from managers import event_manager
from managers.trade_manager import VALID_TRADE_TYPES
from utils.events import EventType, TradeOutcome

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trade", tags=["trade"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fetch_item(item_type: str, item_id: int):
    """Fetch a card or aspect by type and id, raising on invalid type or missing item."""
    if item_type not in VALID_TRADE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid item type: {item_type}")
    if item_type == "card":
        item = await asyncio.to_thread(card_repo.get_card, item_id)
    else:
        item = await asyncio.to_thread(aspect_repo.get_aspect_by_id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"{item_type.capitalize()} not found")
    return item


def _build_view_url(item_type: str, item_id: int) -> str | None:
    """Build a miniapp deep-link URL for viewing a trade item."""
    if not MINIAPP_URL:
        return None
    if item_type == "card":
        return build_single_card_url(item_id)
    return build_single_aspect_url(item_id)


# ---------------------------------------------------------------------------
# Options endpoints
# ---------------------------------------------------------------------------

@router.get("/{offer_type}/{offer_id}/options/cards", response_model=List[APICard])
async def get_trade_card_options(
    offer_type: str,
    offer_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get cards tradeable for the offered item, scoped to the same chat."""
    user_id = validated_user["user"].get("id")

    item = await _fetch_item(offer_type, offer_id)

    if item.user_id != user_id:
        raise HTTPException(status_code=403, detail="You do not own this item")

    if not item.chat_id:
        raise HTTPException(status_code=400, detail="Item has no chat")

    cards = await asyncio.to_thread(card_repo.get_all_cards, item.chat_id)
    return [
        c for c in cards
        if c.id != (offer_id if offer_type == "card" else -1)
        and c.owner is not None
        and c.owner != item.owner
    ]


@router.get("/{offer_type}/{offer_id}/options/aspects", response_model=List[APIAspect])
async def get_trade_aspect_options(
    offer_type: str,
    offer_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get aspects tradeable for the offered item, scoped to the same chat."""
    user_id = validated_user["user"].get("id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid user data")

    item = await _fetch_item(offer_type, offer_id)

    if item.user_id != user_id:
        raise HTTPException(status_code=403, detail="You do not own this item")

    if not item.chat_id:
        raise HTTPException(status_code=400, detail="Item has no chat")

    return await asyncio.to_thread(
        aspect_repo.get_chat_aspects_for_trade, item.chat_id, user_id
    )


# ---------------------------------------------------------------------------
# Execute trade
# ---------------------------------------------------------------------------

@router.post("/{offer_type}/{offer_id}/{want_type}/{want_id}")
async def execute_trade(
    offer_type: str,
    offer_id: int,
    want_type: str,
    want_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Execute a trade between two items and send a request to the chat."""
    if offer_type not in VALID_TRADE_TYPES or want_type not in VALID_TRADE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid item type")

    user_data = validated_user["user"]
    user_id = user_data.get("id")
    current_username = user_data.get("username")
    if not user_id or not current_username:
        raise HTTPException(status_code=400, detail="Invalid user data")

    if not TELEGRAM_TOKEN:
        raise HTTPException(status_code=503, detail="Bot service unavailable")

    try:
        offer_item = await _fetch_item(offer_type, offer_id)
        want_item = await _fetch_item(want_type, want_id)

        if not offer_item.chat_id or not want_item.chat_id:
            raise HTTPException(status_code=500, detail="Item chat not configured")
        if offer_item.chat_id != want_item.chat_id:
            raise HTTPException(status_code=400, detail="Items must be in the same chat")

        if offer_item.owner != current_username:
            raise HTTPException(status_code=403, detail=f"You do not own {offer_item.title()}")
        if want_item.owner == current_username:
            raise HTTPException(status_code=400, detail="You already own this item")

        offer_title = offer_item.title(include_id=True, include_rarity=True, include_emoji=True)
        want_title = want_item.title(include_id=True, include_rarity=True, include_emoji=True)

        trade_message = TRADE_REQUEST_MESSAGE.format(
            user1_username=current_username,
            item1_title=offer_title,
            user2_username=want_item.owner,
            item2_title=want_title,
        )

        keyboard = [
            [
                InlineKeyboardButton("Accept", callback_data=f"trade_accept_{offer_type}_{offer_id}_{want_type}_{want_id}"),
                InlineKeyboardButton("Reject", callback_data=f"trade_reject_{offer_type}_{offer_id}_{want_type}_{want_id}"),
            ]
        ]

        offer_url = _build_view_url(offer_type, offer_id)
        want_url = _build_view_url(want_type, want_id)
        if offer_url and want_url:
            keyboard.append([
                InlineKeyboardButton(f"View {offer_type.capitalize()}", url=offer_url),
                InlineKeyboardButton(f"View {want_type.capitalize()}", url=want_url),
            ])

        try:
            bot = create_bot_instance()

            thread_id = await asyncio.to_thread(thread_repo.get_thread_id, str(offer_item.chat_id), "trade")
            if thread_id is None:
                thread_id = await asyncio.to_thread(thread_repo.get_thread_id, str(offer_item.chat_id), "main")

            send_params: Dict[str, Any] = {
                "chat_id": offer_item.chat_id,
                "text": trade_message,
                "parse_mode": "HTML",
                "reply_markup": InlineKeyboardMarkup(keyboard),
            }
            if thread_id is not None:
                send_params["message_thread_id"] = thread_id

            await bot.send_message(**send_params)

            event_manager.log(
                EventType.TRADE,
                TradeOutcome.CREATED,
                user_id=user_id,
                chat_id=str(offer_item.chat_id),
                target_user=want_item.owner,
                source="miniapp",
                type=f"{offer_type}_for_{want_type}",
            )
        except Exception as e:
            logger.error("Failed to send trade request to chat %s: %s", offer_item.chat_id, e)
            raise HTTPException(status_code=500, detail="Failed to send trade request")

        return {"success": True, "message": "Trade request sent successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error in trade endpoint: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
