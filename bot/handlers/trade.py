"""
Trade-related command handlers.

This module contains handlers for initiating, accepting, and rejecting trades.
Supports both card-for-card and aspect-for-aspect trades.
Cross-type trades (card-for-aspect) are explicitly rejected.
"""

import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from config import DEBUG_MODE, MINIAPP_URL_ENV
from settings.constants import (
    TRADE_REQUEST_MESSAGE,
    TRADE_COMPLETE_MESSAGE,
    TRADE_REJECTED_MESSAGE,
    TRADE_CANCELLED_MESSAGE,
    ASPECT_TRADE_REQUEST_MESSAGE,
    ASPECT_TRADE_COMPLETE_MESSAGE,
    ASPECT_TRADE_REJECTED_MESSAGE,
    ASPECT_TRADE_CANCELLED_MESSAGE,
)
from repos import card_repo
from repos import aspect_repo
from managers import event_manager
from managers import trade_manager
from utils.schemas import User
from utils.decorators import verify_user_in_chat
from utils.miniapp import encode_single_card_token, encode_single_aspect_token
from utils.events import EventType, TradeOutcome

logger = logging.getLogger(__name__)


@verify_user_in_chat
async def trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Initiate a card or aspect trade.

    Syntax:
      /trade <card_id1> <card_id2>           — card-for-card trade
      /trade aspect <aspect_id1> <aspect_id2> — aspect-for-aspect trade
    """

    if update.effective_chat.type == ChatType.PRIVATE and not DEBUG_MODE:
        await update.message.reply_text("Only allowed to trade in the group chat.")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\n"
            "  /trade [your_card_id] [other_card_id]\n"
            "  /trade aspect [your_aspect_id] [other_aspect_id]"
        )
        return

    # Determine trade type
    if context.args[0].lower() == "aspect":
        await _initiate_aspect_trade(update, context, user)
    else:
        await _initiate_card_trade(update, context, user)


async def _initiate_card_trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Initiate a card-for-card trade."""
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /trade [your_card_id] [other_card_id]")
        return

    try:
        card_id1 = int(context.args[0])
        card_id2 = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Card IDs must be numbers.")
        return

    card1 = await asyncio.to_thread(card_repo.get_card, card_id1)
    card2 = await asyncio.to_thread(card_repo.get_card, card_id2)

    if not card1 or not card2:
        await update.message.reply_text("One or both card IDs are invalid.")
        return

    if card1.owner != user.username:
        await update.message.reply_text(
            f"You do not own card <b>{card1.title()}</b>.", parse_mode=ParseMode.HTML
        )
        return

    if card2.owner == user.username:
        await update.message.reply_text(
            f"You already own card <b>{card2.title()}</b>.", parse_mode=ParseMode.HTML
        )
        return

    user2_username = card2.owner

    # Build mini-app card view URLs
    card1_url = None
    card2_url = None
    if MINIAPP_URL_ENV:
        card1_token = encode_single_card_token(card_id1)
        card2_token = encode_single_card_token(card_id2)
        card1_url = f"{MINIAPP_URL_ENV}?startapp={card1_token}"
        card2_url = f"{MINIAPP_URL_ENV}?startapp={card2_token}"

    keyboard = [
        [
            InlineKeyboardButton(
                "Accept", callback_data=f"card_trade_accept_{card_id1}_{card_id2}"
            ),
            InlineKeyboardButton(
                "Reject", callback_data=f"card_trade_reject_{card_id1}_{card_id2}"
            ),
        ]
    ]

    # Add card view links if miniapp_url is available
    if card1_url and card2_url:
        keyboard.append(
            [
                InlineKeyboardButton("Card 1", url=card1_url),
                InlineKeyboardButton("Card 2", url=card2_url),
            ]
        )

    reply_markup = InlineKeyboardMarkup(keyboard)

    chat_id_str = str(update.effective_chat.id)

    # Log trade created
    event_manager.log(
        EventType.TRADE,
        TradeOutcome.CREATED,
        user_id=user.user_id,
        chat_id=chat_id_str,
        card_id=card_id1,
        target_card_id=card_id2,
        target_user=user2_username,
        type="card",
    )

    await update.message.reply_text(
        TRADE_REQUEST_MESSAGE.format(
            user1_username=user.username,
            card1_title=card1.title(include_id=True, include_rarity=True, include_emoji=True),
            user2_username=user2_username,
            card2_title=card2.title(include_id=True, include_rarity=True, include_emoji=True),
        ),
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )


async def _initiate_aspect_trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Initiate an aspect-for-aspect trade."""
    # context.args[0] == "aspect", so ids are at [1] and [2]
    if len(context.args) != 3:
        await update.message.reply_text("Usage: /trade aspect [your_aspect_id] [other_aspect_id]")
        return

    try:
        aspect_id1 = int(context.args[1])
        aspect_id2 = int(context.args[2])
    except ValueError:
        await update.message.reply_text("Aspect IDs must be numbers.")
        return

    aspect1 = await asyncio.to_thread(aspect_repo.get_aspect_by_id, aspect_id1)
    aspect2 = await asyncio.to_thread(aspect_repo.get_aspect_by_id, aspect_id2)

    if not aspect1 or not aspect2:
        await update.message.reply_text("One or both aspect IDs are invalid.")
        return

    if aspect1.owner != user.username:
        await update.message.reply_text(
            f"You do not own aspect <b>{aspect1.display_name}</b>.",
            parse_mode=ParseMode.HTML,
        )
        return

    if aspect2.owner == user.username:
        await update.message.reply_text(
            f"You already own aspect <b>{aspect2.display_name}</b>.",
            parse_mode=ParseMode.HTML,
        )
        return

    user2_username = aspect2.owner

    aspect1_title = aspect1.title(include_id=True, include_rarity=True, include_emoji=True)
    aspect2_title = aspect2.title(include_id=True, include_rarity=True, include_emoji=True)

    # Build mini-app aspect view URLs
    aspect1_url = None
    aspect2_url = None
    if MINIAPP_URL_ENV:
        aspect1_token = encode_single_aspect_token(aspect_id1)
        aspect2_token = encode_single_aspect_token(aspect_id2)
        aspect1_url = f"{MINIAPP_URL_ENV}?startapp={aspect1_token}"
        aspect2_url = f"{MINIAPP_URL_ENV}?startapp={aspect2_token}"

    keyboard = [
        [
            InlineKeyboardButton(
                "Accept", callback_data=f"aspect_trade_accept_{aspect_id1}_{aspect_id2}"
            ),
            InlineKeyboardButton(
                "Reject", callback_data=f"aspect_trade_reject_{aspect_id1}_{aspect_id2}"
            ),
        ]
    ]

    # Add aspect view links if miniapp_url is available
    if aspect1_url and aspect2_url:
        keyboard.append(
            [
                InlineKeyboardButton("Aspect 1", url=aspect1_url),
                InlineKeyboardButton("Aspect 2", url=aspect2_url),
            ]
        )

    reply_markup = InlineKeyboardMarkup(keyboard)

    chat_id_str = str(update.effective_chat.id)

    # Log trade created
    event_manager.log(
        EventType.TRADE,
        TradeOutcome.CREATED,
        user_id=user.user_id,
        chat_id=chat_id_str,
        aspect_id=aspect_id1,
        target_aspect_id=aspect_id2,
        target_user=user2_username,
        type="aspect",
    )

    await update.message.reply_text(
        ASPECT_TRADE_REQUEST_MESSAGE.format(
            user1_username=user.username,
            aspect1_title=aspect1_title,
            user2_username=user2_username,
            aspect2_title=aspect2_title,
        ),
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )


@verify_user_in_chat
async def reject_card_trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle card trade rejection or cancellation (if initiator)."""
    query = update.callback_query

    # callback_data: card_trade_reject_{card_id1}_{card_id2}
    parts = query.data.split("_")
    # parts: ["card", "trade", "reject", card_id1, card_id2]
    card_id1 = int(parts[3])
    card_id2 = int(parts[4])

    card1 = await asyncio.to_thread(card_repo.get_card, card_id1)
    card2 = await asyncio.to_thread(card_repo.get_card, card_id2)

    if not card1 or not card2:
        await query.answer()
        error_text = (
            f"{query.message.text}\n\n❌ <b>Trade failed: one of the cards no longer exists.</b>"
        )
        await query.edit_message_text(error_text, parse_mode=ParseMode.HTML)
        return

    user1_username = card1.owner
    user2_username = card2.owner

    # Check if the user pressing Reject is the initiator (card1 owner)
    is_initiator = user.username == user1_username

    # If not the initiator, verify they own card2
    if not is_initiator and not DEBUG_MODE and user.username != user2_username:
        await query.answer("You are not the owner of the card being traded for.", show_alert=True)
        return

    chat_id_str = str(query.message.chat_id)

    # Use TRADE_CANCELLED_MESSAGE if initiator pressed Reject, otherwise TRADE_REJECTED_MESSAGE
    if is_initiator:
        message_text = TRADE_CANCELLED_MESSAGE.format(
            user1_username=user1_username,
            card1_title=card1.title(include_id=True, include_rarity=True, include_emoji=True),
            user2_username=user2_username,
            card2_title=card2.title(include_id=True, include_rarity=True, include_emoji=True),
        )
        event_manager.log(
            EventType.TRADE,
            TradeOutcome.CANCELLED,
            user_id=user.user_id,
            chat_id=chat_id_str,
            card_id=card_id1,
            target_card_id=card_id2,
            target_user=user2_username,
            type="card",
        )
    else:
        message_text = TRADE_REJECTED_MESSAGE.format(
            user1_username=user1_username,
            card1_title=card1.title(include_id=True, include_rarity=True, include_emoji=True),
            user2_username=user2_username,
            card2_title=card2.title(include_id=True, include_rarity=True, include_emoji=True),
        )
        event_manager.log(
            EventType.TRADE,
            TradeOutcome.REJECTED,
            user_id=user.user_id,
            chat_id=chat_id_str,
            card_id=card_id2,
            target_card_id=card_id1,
            target_user=user1_username,
            type="card",
        )

    # Extract Card 1 and Card 2 buttons from original message (skip Accept/Reject row)
    reply_markup = None
    if query.message.reply_markup and len(query.message.reply_markup.inline_keyboard) > 1:
        keyboard = [query.message.reply_markup.inline_keyboard[1]]
        reply_markup = InlineKeyboardMarkup(keyboard)

    await query.answer()
    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        message_thread_id=query.message.message_thread_id,
        text=message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
    )


@verify_user_in_chat
async def accept_card_trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle card trade acceptance."""
    query = update.callback_query

    # callback_data: card_trade_accept_{card_id1}_{card_id2}
    parts = query.data.split("_")
    card_id1 = int(parts[3])
    card_id2 = int(parts[4])

    card1 = await asyncio.to_thread(card_repo.get_card, card_id1)
    card2 = await asyncio.to_thread(card_repo.get_card, card_id2)

    if not card1 or not card2:
        await query.answer()
        error_text = f"{query.message.text}\n\n❌ Trade failed: one of the cards no longer exists."
        await query.edit_message_text(error_text, parse_mode=ParseMode.HTML)
        return

    user1_username = card1.owner
    user2_username = card2.owner

    if not DEBUG_MODE and user.username != user2_username:
        await query.answer("You are not the owner of the card being traded for.", show_alert=True)
        return

    error = await asyncio.to_thread(trade_manager.trade_cards, card_id1, card_id2)

    chat_id_str = str(query.message.chat_id)

    if error is None:
        message_text = TRADE_COMPLETE_MESSAGE.format(
            user1_username=user1_username,
            card1_title=card1.title(include_id=True, include_rarity=True, include_emoji=True),
            user2_username=user2_username,
            card2_title=card2.title(include_id=True, include_rarity=True, include_emoji=True),
        )
        event_manager.log(
            EventType.TRADE,
            TradeOutcome.ACCEPTED,
            user_id=user.user_id,
            chat_id=chat_id_str,
            card_id=card_id2,
            target_card_id=card_id1,
            target_user=user1_username,
            type="card",
        )
    else:
        message_text = f"Trade failed: {error}"
        event_manager.log(
            EventType.TRADE,
            TradeOutcome.ERROR,
            user_id=user.user_id,
            chat_id=chat_id_str,
            card_id=card_id2,
            target_card_id=card_id1,
            target_user=user1_username,
            error_message="trade_manager.trade_cards failed",
            type="card",
        )

    # Extract Card 1 and Card 2 buttons from original message (skip Accept/Reject row)
    reply_markup = None
    if query.message.reply_markup and len(query.message.reply_markup.inline_keyboard) > 1:
        keyboard = [query.message.reply_markup.inline_keyboard[1]]
        reply_markup = InlineKeyboardMarkup(keyboard)

    await query.answer()
    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        message_thread_id=query.message.message_thread_id,
        text=message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
    )


# ---------------------------------------------------------------------------
# Aspect trade callbacks
# ---------------------------------------------------------------------------


@verify_user_in_chat
async def reject_aspect_trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle aspect trade rejection or cancellation (if initiator)."""
    query = update.callback_query

    # callback_data: aspect_trade_reject_{aspect_id1}_{aspect_id2}
    parts = query.data.split("_")
    # parts: ["aspect", "trade", "reject", aspect_id1, aspect_id2]
    aspect_id1 = int(parts[3])
    aspect_id2 = int(parts[4])

    aspect1 = await asyncio.to_thread(aspect_repo.get_aspect_by_id, aspect_id1)
    aspect2 = await asyncio.to_thread(aspect_repo.get_aspect_by_id, aspect_id2)

    if not aspect1 or not aspect2:
        await query.answer()
        error_text = (
            f"{query.message.text}\n\n❌ <b>Trade failed: one of the aspects no longer exists.</b>"
        )
        await query.edit_message_text(error_text, parse_mode=ParseMode.HTML)
        return

    user1_username = aspect1.owner
    user2_username = aspect2.owner

    aspect1_title = aspect1.title(include_id=True, include_rarity=True, include_emoji=True)
    aspect2_title = aspect2.title(include_id=True, include_rarity=True, include_emoji=True)

    is_initiator = user.username == user1_username

    if not is_initiator and not DEBUG_MODE and user.username != user2_username:
        await query.answer("You are not the owner of the aspect being traded for.", show_alert=True)
        return

    chat_id_str = str(query.message.chat_id)

    if is_initiator:
        message_text = ASPECT_TRADE_CANCELLED_MESSAGE.format(
            user1_username=user1_username,
            aspect1_title=aspect1_title,
            user2_username=user2_username,
            aspect2_title=aspect2_title,
        )
        event_manager.log(
            EventType.TRADE,
            TradeOutcome.CANCELLED,
            user_id=user.user_id,
            chat_id=chat_id_str,
            aspect_id=aspect_id1,
            target_aspect_id=aspect_id2,
            target_user=user2_username,
            type="aspect",
        )
    else:
        message_text = ASPECT_TRADE_REJECTED_MESSAGE.format(
            user1_username=user1_username,
            aspect1_title=aspect1_title,
            user2_username=user2_username,
            aspect2_title=aspect2_title,
        )
        event_manager.log(
            EventType.TRADE,
            TradeOutcome.REJECTED,
            user_id=user.user_id,
            chat_id=chat_id_str,
            aspect_id=aspect_id2,
            target_aspect_id=aspect_id1,
            target_user=user1_username,
            type="aspect",
        )

    # Extract Aspect 1 and Aspect 2 buttons from original message (skip Accept/Reject row)
    reply_markup = None
    if query.message.reply_markup and len(query.message.reply_markup.inline_keyboard) > 1:
        keyboard = [query.message.reply_markup.inline_keyboard[1]]
        reply_markup = InlineKeyboardMarkup(keyboard)

    await query.answer()
    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        message_thread_id=query.message.message_thread_id,
        text=message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
    )


@verify_user_in_chat
async def accept_aspect_trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle aspect trade acceptance."""
    query = update.callback_query

    # callback_data: aspect_trade_accept_{aspect_id1}_{aspect_id2}
    parts = query.data.split("_")
    aspect_id1 = int(parts[3])
    aspect_id2 = int(parts[4])

    aspect1 = await asyncio.to_thread(aspect_repo.get_aspect_by_id, aspect_id1)
    aspect2 = await asyncio.to_thread(aspect_repo.get_aspect_by_id, aspect_id2)

    if not aspect1 or not aspect2:
        await query.answer()
        error_text = (
            f"{query.message.text}\n\n❌ Trade failed: one of the aspects no longer exists."
        )
        await query.edit_message_text(error_text, parse_mode=ParseMode.HTML)
        return

    user1_username = aspect1.owner
    user2_username = aspect2.owner

    aspect1_title = aspect1.title(include_id=True, include_rarity=True, include_emoji=True)
    aspect2_title = aspect2.title(include_id=True, include_rarity=True, include_emoji=True)

    if not DEBUG_MODE and user.username != user2_username:
        await query.answer("You are not the owner of the aspect being traded for.", show_alert=True)
        return

    error = await asyncio.to_thread(trade_manager.trade_aspects, aspect_id1, aspect_id2)

    chat_id_str = str(query.message.chat_id)

    if error is None:
        message_text = ASPECT_TRADE_COMPLETE_MESSAGE.format(
            user1_username=user1_username,
            aspect1_title=aspect1_title,
            user2_username=user2_username,
            aspect2_title=aspect2_title,
        )
        event_manager.log(
            EventType.TRADE,
            TradeOutcome.ACCEPTED,
            user_id=user.user_id,
            chat_id=chat_id_str,
            aspect_id=aspect_id2,
            target_aspect_id=aspect_id1,
            target_user=user1_username,
            type="aspect",
        )
    else:
        message_text = f"Aspect trade failed: {error}"
        event_manager.log(
            EventType.TRADE,
            TradeOutcome.ERROR,
            user_id=user.user_id,
            chat_id=chat_id_str,
            aspect_id=aspect_id2,
            target_aspect_id=aspect_id1,
            target_user=user1_username,
            error_message="trade_manager.trade_aspects failed",
            type="aspect",
        )

    # Extract Aspect 1 and Aspect 2 buttons from original message (skip Accept/Reject row)
    reply_markup = None
    if query.message.reply_markup and len(query.message.reply_markup.inline_keyboard) > 1:
        keyboard = [query.message.reply_markup.inline_keyboard[1]]
        reply_markup = InlineKeyboardMarkup(keyboard)

    await query.answer()
    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        message_thread_id=query.message.message_thread_id,
        text=message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
    )
