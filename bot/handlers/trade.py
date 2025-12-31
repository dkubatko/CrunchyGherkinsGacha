"""
Trade-related command handlers.

This module contains handlers for initiating, accepting, and rejecting trades.
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
)
from utils.services import card_service, event_service
from utils.schemas import User
from utils.decorators import verify_user_in_chat
from utils.miniapp import encode_single_card_token
from utils.events import EventType, TradeOutcome

logger = logging.getLogger(__name__)


@verify_user_in_chat
async def trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Initiate a card trade."""

    if update.effective_chat.type == ChatType.PRIVATE and not DEBUG_MODE:
        await update.message.reply_text("Only allowed to trade in the group chat.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: /trade [your_card_id] [other_card_id]")
        return

    try:
        card_id1 = int(context.args[0])
        card_id2 = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Card IDs must be numbers.")
        return

    card1 = await asyncio.to_thread(card_service.get_card, card_id1)
    card2 = await asyncio.to_thread(card_service.get_card, card_id2)

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
            InlineKeyboardButton("Accept", callback_data=f"trade_accept_{card_id1}_{card_id2}"),
            InlineKeyboardButton("Reject", callback_data=f"trade_reject_{card_id1}_{card_id2}"),
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
    event_service.log(
        EventType.TRADE,
        TradeOutcome.CREATED,
        user_id=user.user_id,
        chat_id=chat_id_str,
        card_id=card_id1,
        target_card_id=card_id2,
        target_user=user2_username,
    )

    await update.message.reply_text(
        TRADE_REQUEST_MESSAGE.format(
            user1_username=user.username,
            card1_title=card1.title(include_rarity=True),
            user2_username=user2_username,
            card2_title=card2.title(include_rarity=True),
        ),
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )


@verify_user_in_chat
async def reject_trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle trade rejection or cancellation (if initiator)."""
    query = update.callback_query

    _, _, card_id1_str, card_id2_str = query.data.split("_")
    card_id1 = int(card_id1_str)
    card_id2 = int(card_id2_str)

    card1 = await asyncio.to_thread(card_service.get_card, card_id1)
    card2 = await asyncio.to_thread(card_service.get_card, card_id2)

    if not card1 or not card2:
        await query.answer()
        # Append error to original message
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
            card1_title=card1.title(include_rarity=True),
            user2_username=user2_username,
            card2_title=card2.title(include_rarity=True),
        )
        # Log trade cancelled by initiator
        event_service.log(
            EventType.TRADE,
            TradeOutcome.CANCELLED,
            user_id=user.user_id,
            chat_id=chat_id_str,
            card_id=card_id1,
            target_card_id=card_id2,
            target_user=user2_username,
        )
    else:
        message_text = TRADE_REJECTED_MESSAGE.format(
            user1_username=user1_username,
            card1_title=card1.title(include_rarity=True),
            user2_username=user2_username,
            card2_title=card2.title(include_rarity=True),
        )
        # Log trade rejected by target user
        event_service.log(
            EventType.TRADE,
            TradeOutcome.REJECTED,
            user_id=user.user_id,
            chat_id=chat_id_str,
            card_id=card_id2,
            target_card_id=card_id1,
            target_user=user1_username,
        )

    # Extract Card 1 and Card 2 buttons from original message (skip Accept/Reject row)
    reply_markup = None
    if query.message.reply_markup and len(query.message.reply_markup.inline_keyboard) > 1:
        # Keep only the second row (Card 1 and Card 2 buttons)
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
async def accept_trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle trade acceptance."""
    query = update.callback_query

    _, _, card_id1_str, card_id2_str = query.data.split("_")
    card_id1 = int(card_id1_str)
    card_id2 = int(card_id2_str)

    card1 = await asyncio.to_thread(card_service.get_card, card_id1)
    card2 = await asyncio.to_thread(card_service.get_card, card_id2)

    if not card1 or not card2:
        await query.answer()
        # Append error to original message
        error_text = f"{query.message.text}\n\n❌ Trade failed: one of the cards no longer exists."
        await query.edit_message_text(error_text, parse_mode=ParseMode.HTML)
        return

    user1_username = card1.owner
    user2_username = card2.owner

    if not DEBUG_MODE and user.username != user2_username:
        await query.answer("You are not the owner of the card being traded for.", show_alert=True)
        return

    success = await asyncio.to_thread(card_service.swap_card_owners, card_id1, card_id2)

    chat_id_str = str(query.message.chat_id)

    if success:
        message_text = TRADE_COMPLETE_MESSAGE.format(
            user1_username=user1_username,
            card1_title=card1.title(include_rarity=True),
            user2_username=user2_username,
            card2_title=card2.title(include_rarity=True),
        )
        # Log successful trade (from acceptor's perspective)
        event_service.log(
            EventType.TRADE,
            TradeOutcome.ACCEPTED,
            user_id=user.user_id,
            chat_id=chat_id_str,
            card_id=card_id2,
            target_card_id=card_id1,
            target_user=user1_username,
        )
    else:
        message_text = "Trade failed. Please try again."
        # Log trade error
        event_service.log(
            EventType.TRADE,
            TradeOutcome.ERROR,
            user_id=user.user_id,
            chat_id=chat_id_str,
            card_id=card_id2,
            target_card_id=card_id1,
            target_user=user1_username,
            error_message="swap_card_owners failed",
        )

    # Extract Card 1 and Card 2 buttons from original message (skip Accept/Reject row)
    reply_markup = None
    if query.message.reply_markup and len(query.message.reply_markup.inline_keyboard) > 1:
        # Keep only the second row (Card 1 and Card 2 buttons)
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
