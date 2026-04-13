"""Trade-related command handlers.

Unified trade flow: every trade is (offer_type, offer_id) ↔ (want_type, want_id)
where types are ``card`` or ``aspect``.

Bot command:  /trade <offer_type> <offer_id> <want_type> <want_id>
Callbacks:    trade_accept_{offer_type}_{offer_id}_{want_type}_{want_id}
              trade_reject_{offer_type}_{offer_id}_{want_type}_{want_id}
"""

import asyncio
import logging
from typing import Optional, Tuple, Union

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from config import DEBUG_MODE, MINIAPP_URL_ENV
from settings.constants import (
    TRADE_REQUEST_MESSAGE,
    TRADE_COMPLETE_MESSAGE,
    TRADE_REJECTED_MESSAGE,
    TRADE_CANCELLED_MESSAGE,
    TRADE_USAGE_MESSAGE,
)
from repos import card_repo, aspect_repo
from managers import event_manager, trade_manager
from managers.trade_manager import TradeItemType, VALID_TRADE_TYPES
from utils.schemas import Card, OwnedAspect, User
from utils.decorators import verify_user_in_chat
from utils.miniapp import encode_single_card_token, encode_single_aspect_token
from utils.events import EventType, TradeOutcome

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fetch_item(
    item_type: TradeItemType, item_id: int
) -> Optional[Union[Card, OwnedAspect]]:
    """Fetch a card or aspect by type and id."""
    if item_type == "card":
        return await asyncio.to_thread(card_repo.get_card, item_id)
    return await asyncio.to_thread(aspect_repo.get_aspect_by_id, item_id)


def _build_view_url(item_type: TradeItemType, item_id: int) -> Optional[str]:
    """Build a miniapp deep-link URL for viewing a trade item."""
    if not MINIAPP_URL_ENV:
        return None
    token = encode_single_card_token(item_id) if item_type == "card" else encode_single_aspect_token(item_id)
    return f"{MINIAPP_URL_ENV}?startapp={token}"


def _parse_callback(data: str) -> Optional[Tuple[str, TradeItemType, int, TradeItemType, int]]:
    """Parse ``trade_{action}_{offer_type}_{offer_id}_{want_type}_{want_id}``.

    Returns (action, offer_type, offer_id, want_type, want_id) or None on failure.
    """
    parts = data.split("_")
    if len(parts) != 6:
        return None
    _, action, offer_type, offer_id_str, want_type, want_id_str = parts
    if action not in ("accept", "reject"):
        return None
    if offer_type not in VALID_TRADE_TYPES or want_type not in VALID_TRADE_TYPES:
        return None
    try:
        offer_id = int(offer_id_str)
        want_id = int(want_id_str)
    except ValueError:
        return None
    if offer_id <= 0 or want_id <= 0:
        return None
    return action, offer_type, offer_id, want_type, want_id


def _build_trade_keyboard(
    offer_type: TradeItemType, offer_id: int,
    want_type: TradeItemType, want_id: int,
) -> InlineKeyboardMarkup:
    """Build the Accept/Reject + View keyboard for a trade message."""
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
    return InlineKeyboardMarkup(keyboard)


def _strip_action_row(message) -> Optional[InlineKeyboardMarkup]:
    """Keep view-link row from a trade message, remove Accept/Reject row."""
    if message.reply_markup and len(message.reply_markup.inline_keyboard) > 1:
        return InlineKeyboardMarkup([message.reply_markup.inline_keyboard[1]])
    return None


def _build_event_kwargs(item_type: TradeItemType, item_id: int, *, prefix: str = "") -> dict:
    """Build event_manager.log keyword args for a trade item."""
    key = f"{prefix}{'card_id' if item_type == 'card' else 'aspect_id'}"
    return {key: item_id}


def _log_trade_event(
    outcome: TradeOutcome,
    user_id: int,
    chat_id: str,
    offer_type: TradeItemType, offer_id: int,
    want_type: TradeItemType, want_id: int,
    target_user: str,
    *,
    error_message: Optional[str] = None,
) -> None:
    """Log a trade event with consistent kwargs."""
    kwargs = {
        **_build_event_kwargs(offer_type, offer_id),
        **_build_event_kwargs(want_type, want_id, prefix="target_"),
    }
    if error_message:
        kwargs["error_message"] = error_message
    event_manager.log(
        EventType.TRADE,
        outcome,
        user_id=user_id,
        chat_id=chat_id,
        target_user=target_user,
        type=f"{offer_type}_for_{want_type}",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# /trade command
# ---------------------------------------------------------------------------

@verify_user_in_chat
async def trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Initiate a trade.

    Syntax: /trade <offer_type> <offer_id> <want_type> <want_id>
    """
    if update.effective_chat.type == ChatType.PRIVATE and not DEBUG_MODE:
        await update.message.reply_text("Only allowed to trade in the group chat.")
        return

    args = context.args or []
    if len(args) != 4:
        await update.message.reply_text(TRADE_USAGE_MESSAGE)
        return

    offer_type_raw, offer_id_raw, want_type_raw, want_id_raw = args

    if offer_type_raw.lower() not in VALID_TRADE_TYPES or want_type_raw.lower() not in VALID_TRADE_TYPES:
        await update.message.reply_text(TRADE_USAGE_MESSAGE)
        return

    offer_type: TradeItemType = offer_type_raw.lower()
    want_type: TradeItemType = want_type_raw.lower()

    try:
        offer_id = int(offer_id_raw)
        want_id = int(want_id_raw)
    except ValueError:
        await update.message.reply_text("IDs must be numbers.")
        return

    offer_item = await _fetch_item(offer_type, offer_id)
    want_item = await _fetch_item(want_type, want_id)

    if not offer_item or not want_item:
        await update.message.reply_text("One or both IDs are invalid.")
        return

    if offer_item.owner != user.username:
        await update.message.reply_text(
            f"You do not own {offer_type} <b>{offer_item.title()}</b>.",
            parse_mode=ParseMode.HTML,
        )
        return

    if want_item.owner == user.username:
        await update.message.reply_text(
            f"You already own {want_type} <b>{want_item.title()}</b>.",
            parse_mode=ParseMode.HTML,
        )
        return

    offer_title = offer_item.title(include_id=True, include_rarity=True, include_emoji=True)
    want_title = want_item.title(include_id=True, include_rarity=True, include_emoji=True)
    chat_id_str = str(update.effective_chat.id)

    _log_trade_event(
        TradeOutcome.CREATED, user.user_id, chat_id_str,
        offer_type, offer_id, want_type, want_id,
        target_user=want_item.owner,
    )

    await update.message.reply_text(
        TRADE_REQUEST_MESSAGE.format(
            user1_username=user.username,
            item1_title=offer_title,
            user2_username=want_item.owner,
            item2_title=want_title,
        ),
        reply_markup=_build_trade_keyboard(offer_type, offer_id, want_type, want_id),
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# Unified accept / reject callbacks
# ---------------------------------------------------------------------------

@verify_user_in_chat
async def accept_trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle trade acceptance (any type combination)."""
    query = update.callback_query
    parsed = _parse_callback(query.data)
    if not parsed:
        await query.answer("Invalid trade data.", show_alert=True)
        return

    _, offer_type, offer_id, want_type, want_id = parsed

    offer_item = await _fetch_item(offer_type, offer_id)
    want_item = await _fetch_item(want_type, want_id)

    if not offer_item or not want_item:
        await query.answer()
        await query.edit_message_text(
            f"{query.message.text}\n\n❌ Trade failed: one of the items no longer exists.",
            parse_mode=ParseMode.HTML,
        )
        return

    if not DEBUG_MODE and user.user_id != want_item.user_id:
        await query.answer("You are not the owner of the requested item.", show_alert=True)
        return

    offer_title = offer_item.title(include_id=True, include_rarity=True, include_emoji=True)
    want_title = want_item.title(include_id=True, include_rarity=True, include_emoji=True)

    error = await asyncio.to_thread(
        trade_manager.execute_trade, offer_type, offer_id, want_type, want_id
    )

    chat_id_str = str(query.message.chat_id)

    if error is None:
        message_text = TRADE_COMPLETE_MESSAGE.format(
            user1_username=offer_item.owner,
            item1_title=offer_title,
            user2_username=want_item.owner,
            item2_title=want_title,
        )
        _log_trade_event(
            TradeOutcome.ACCEPTED, user.user_id, chat_id_str,
            offer_type, offer_id, want_type, want_id,
            target_user=offer_item.owner,
        )
    else:
        message_text = f"Trade failed: {error}"
        _log_trade_event(
            TradeOutcome.ERROR, user.user_id, chat_id_str,
            offer_type, offer_id, want_type, want_id,
            target_user=offer_item.owner,
            error_message=error,
        )

    await query.answer()
    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        message_thread_id=query.message.message_thread_id,
        text=message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=_strip_action_row(query.message),
    )


@verify_user_in_chat
async def reject_trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle trade rejection or cancellation (if initiator)."""
    query = update.callback_query
    parsed = _parse_callback(query.data)
    if not parsed:
        await query.answer("Invalid trade data.", show_alert=True)
        return

    _, offer_type, offer_id, want_type, want_id = parsed

    offer_item = await _fetch_item(offer_type, offer_id)
    want_item = await _fetch_item(want_type, want_id)

    if not offer_item or not want_item:
        await query.answer()
        await query.edit_message_text(
            f"{query.message.text}\n\n❌ <b>Trade failed: one of the items no longer exists.</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    is_initiator = user.user_id == offer_item.user_id

    if not is_initiator and not DEBUG_MODE and user.user_id != want_item.user_id:
        await query.answer("You are not involved in this trade.", show_alert=True)
        return

    offer_title = offer_item.title(include_id=True, include_rarity=True, include_emoji=True)
    want_title = want_item.title(include_id=True, include_rarity=True, include_emoji=True)
    chat_id_str = str(query.message.chat_id)

    if is_initiator:
        message_text = TRADE_CANCELLED_MESSAGE.format(
            user1_username=offer_item.owner,
            item1_title=offer_title,
            user2_username=want_item.owner,
            item2_title=want_title,
        )
        _log_trade_event(
            TradeOutcome.CANCELLED, user.user_id, chat_id_str,
            offer_type, offer_id, want_type, want_id,
            target_user=want_item.owner,
        )
    else:
        message_text = TRADE_REJECTED_MESSAGE.format(
            user1_username=offer_item.owner,
            item1_title=offer_title,
            user2_username=want_item.owner,
            item2_title=want_title,
        )
        _log_trade_event(
            TradeOutcome.REJECTED, user.user_id, chat_id_str,
            offer_type, offer_id, want_type, want_id,
            target_user=offer_item.owner,
        )

    await query.answer()
    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        message_thread_id=query.message.message_thread_id,
        text=message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=_strip_action_row(query.message),
    )
