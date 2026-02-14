"""
Collection-related command handlers.

This module contains handlers for viewing collections, balance, stats, and casino.
"""

import asyncio
import base64
import logging
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from config import DEBUG_MODE, MINIAPP_URL_ENV
from handlers.helpers import save_card_file_id_from_message
from settings.constants import COLLECTION_CAPTION
from utils.services import card_service, user_service, claim_service, spin_service
from utils.schemas import User
from utils.decorators import verify_user, verify_user_in_chat
from utils.miniapp import encode_miniapp_token, encode_casino_token

logger = logging.getLogger(__name__)


@verify_user_in_chat
async def casino(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Open the casino mini-app with catalog view."""

    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("/casino can only be used in group chats.")
        return

    # Generate casino token with user_id and chat_id
    chat_id = str(chat.id)
    casino_token = encode_casino_token(user.user_id, chat_id)

    # Create WebApp button
    if not MINIAPP_URL_ENV:
        await message.reply_text("Casino mini-app is not configured.")
        return

    app_url = f"{MINIAPP_URL_ENV}?startapp={casino_token}"
    keyboard = [[InlineKeyboardButton("🎰 Open Casino!", url=app_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text("🎰 Ready to play at the casino?", reply_markup=reply_markup)


@verify_user_in_chat
async def balance(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Report claim balance for the calling user or a specified username."""
    message = update.effective_message
    chat = update.effective_chat

    if not chat or chat.type == ChatType.PRIVATE:
        if message:
            await message.reply_text(
                "Claim balances are tracked per group chat. Use this command inside a chat.",
                reply_to_message_id=getattr(message, "message_id", None),
            )
        return

    chat_id = str(chat.id)

    target_user_id: int
    display_username: Optional[str] = None

    if context.args and len(context.args) > 0:
        target_username = context.args[0].lstrip("@")
        target_user_id = await asyncio.to_thread(
            user_service.get_user_id_by_username, target_username
        )
        if target_user_id is None:
            if message:
                await message.reply_text(
                    f"@{target_username} doesn't exist or isn't enrolled yet.",
                    reply_to_message_id=getattr(message, "message_id", None),
                )
            return

        is_member = await asyncio.to_thread(user_service.is_user_in_chat, chat_id, target_user_id)
        if not is_member:
            if message:
                await message.reply_text(
                    f"@{target_username} isn't enrolled in this chat.",
                    reply_to_message_id=getattr(message, "message_id", None),
                )
            return

        resolved_username = await asyncio.to_thread(
            user_service.get_username_for_user_id, target_user_id
        )
        display_username = resolved_username or target_username
    else:
        target_user_id = user.user_id
        display_username = user.username

    balance_value = await asyncio.to_thread(
        claim_service.get_claim_balance, target_user_id, chat_id
    )
    point_label = "point" if balance_value == 1 else "points"

    spin_count = await asyncio.to_thread(
        spin_service.get_user_spin_count,
        target_user_id,
        chat_id,
    )
    spin_label = "spin" if spin_count == 1 else "spins"

    claim_line = f"Claim balance: <b>{balance_value} {point_label}</b>"
    spin_line = f"Spin balance: <b>{spin_count} {spin_label}</b>"

    if target_user_id == user.user_id:
        response_text = f"{claim_line}\n{spin_line}"
        if balance_value == 0:
            response_text += "\n\nUse /roll to get a claim point!"
    else:
        handle = f"@{display_username}" if display_username else str(target_user_id)
        response_text = f"{handle}\n{claim_line}\n{spin_line}"

    if message:
        await message.reply_text(
            response_text,
            reply_to_message_id=getattr(message, "message_id", None),
            parse_mode=ParseMode.HTML,
        )


@verify_user
async def collection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Display user's card collection."""

    chat = update.effective_chat
    chat_id_filter = None
    if chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        chat_id_filter = str(chat.id)
    if chat and chat.type != ChatType.PRIVATE:
        is_member = await asyncio.to_thread(
            user_service.is_user_in_chat, str(chat.id), user.user_id
        )
        if not is_member:
            prompt = "You're not enrolled in this chat yet. Use /enroll in this chat to join."
            if update.callback_query:
                await update.callback_query.answer(prompt, show_alert=True)
            effective_message = update.effective_message
            if effective_message:
                await effective_message.reply_text(prompt)
            return

    # Check if a username argument was provided
    if context.args and len(context.args) > 0:
        if not chat_id_filter:
            if update.message:
                await update.message.reply_text(
                    "Viewing another player's collection is only available in group chats.",
                    reply_to_message_id=update.message.message_id,
                )
            return

        target_username = context.args[0].lstrip("@")  # Remove @ if present
        target_user_id = await asyncio.to_thread(
            user_service.get_user_id_by_username, target_username
        )
        if target_user_id is None:
            await update.message.reply_text(
                f"@{target_username} doesn't exist or isn't enrolled yet.",
                reply_to_message_id=update.message.message_id,
            )
            return

        # Check if the target user exists by trying to get their collection
        target_cards = await asyncio.to_thread(
            card_service.get_user_collection, target_user_id, chat_id_filter
        )
        if not target_cards:
            await update.message.reply_text(
                (
                    f"@{target_username} doesn't have any cards in this chat yet."
                    if chat_id_filter
                    else f"@{target_username} doesn't exist or doesn't own any cards yet."
                ),
                reply_to_message_id=update.message.message_id,
            )
            return
        cards = target_cards
        resolved_username = await asyncio.to_thread(
            user_service.get_username_for_user_id, target_user_id
        )
        display_username = resolved_username or target_username
        viewed_user_id = target_user_id
    else:
        # Default to current user's collection
        cards = await asyncio.to_thread(
            card_service.get_user_collection, user.user_id, chat_id_filter
        )
        resolved_username = await asyncio.to_thread(
            user_service.get_username_for_user_id, user.user_id
        )
        display_username = resolved_username or user.username
        viewed_user_id = user.user_id

        if not cards and not update.callback_query:
            await update.message.reply_text(
                (
                    "You don't own any cards in this chat yet. Use /roll to get your first card!"
                    if chat_id_filter
                    else "You don't own any cards yet. Use /roll to get your first card!"
                ),
                reply_to_message_id=update.message.message_id,
            )
            return

    # For callback queries, we should not be here - they're handled by the navigation handler
    if update.callback_query:
        await update.callback_query.answer(
            "Use the navigation handler for this action.", show_alert=True
        )
        return

    handle_username = display_username or None
    prompt_text = (
        f"View @{handle_username}'s collection" if handle_username else "Select view for collection"
    )

    keyboard_rows = []
    first_row = []
    if MINIAPP_URL_ENV:
        token = encode_miniapp_token(viewed_user_id, chat_id_filter)
        app_url = f"{MINIAPP_URL_ENV}?startapp={token}"
        first_row.append(InlineKeyboardButton("View in app", url=app_url))

    first_row.append(
        InlineKeyboardButton(
            "Show in chat",
            callback_data=f"collection_show_{user.user_id}_{viewed_user_id}",
        )
    )
    keyboard_rows.append(first_row)

    # Second row: "Close" button
    keyboard_rows.append(
        [
            InlineKeyboardButton(
                "Close",
                callback_data=f"collection_dismiss_{user.user_id}",
            )
        ]
    )

    reply_markup = InlineKeyboardMarkup(keyboard_rows)

    message = update.message or update.effective_message
    if message:
        await message.reply_text(
            prompt_text,
            reply_markup=reply_markup,
            reply_to_message_id=getattr(message, "message_id", None),
        )


@verify_user
async def handle_collection_show(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle showing collection in chat."""
    query = update.callback_query
    if not query:
        return

    chat = update.effective_chat
    chat_id_filter = None
    if chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        chat_id_filter = str(chat.id)
    if chat and chat.type != ChatType.PRIVATE:
        is_member = await asyncio.to_thread(
            user_service.is_user_in_chat, str(chat.id), user.user_id
        )
        if not is_member:
            await query.answer(
                "You're not enrolled in this chat yet. Use /enroll in this chat to join.",
                show_alert=True,
            )
            return

    callback_data_parts = query.data.split("_")
    if len(callback_data_parts) < 4:
        await query.answer("Invalid callback format. Please try again.", show_alert=True)
        return

    original_user_id = int(callback_data_parts[2])
    viewed_user_id = int(callback_data_parts[3])

    if user.user_id != original_user_id:
        await query.answer("You can only open collections you requested!", show_alert=True)
        return

    cards = await asyncio.to_thread(
        card_service.get_user_collection, viewed_user_id, chat_id_filter
    )
    if not cards:
        await query.answer("No cards found.", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    resolved_username = await asyncio.to_thread(
        user_service.get_username_for_user_id, viewed_user_id
    )
    display_username = resolved_username or f"user_{viewed_user_id}"

    collection_indices = context.user_data.setdefault("collection_index", {})
    collection_key = (viewed_user_id, chat_id_filter)
    collection_indices[collection_key] = 0

    card_with_image = await asyncio.to_thread(card_service.get_card, cards[0].id)
    if not card_with_image:
        await query.answer("Card not found.", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    card = cards[0]
    lock_icon = "🔒 " if card.locked else ""
    caption = COLLECTION_CAPTION.format(
        lock_icon=lock_icon,
        card_id=card.id,
        card_title=card.title(),
        rarity=card.rarity,
        set_name=(card.set_name or "").title(),
        current_index=1,
        total_cards=len(cards),
        username=display_username,
    )

    keyboard = []
    if len(cards) > 1:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "Prev", callback_data=f"collection_prev_{user.user_id}_{viewed_user_id}"
                ),
                InlineKeyboardButton(
                    "Next", callback_data=f"collection_next_{user.user_id}_{viewed_user_id}"
                ),
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "Close", callback_data=f"collection_close_{user.user_id}_{viewed_user_id}"
            )
        ]
    )
    reply_markup = InlineKeyboardMarkup(keyboard)

    media = card_with_image.get_media()

    query_message = query.message
    reply_target = getattr(query_message, "reply_to_message", None)
    reply_to_message_id = getattr(reply_target, "message_id", None)
    chat_id = getattr(query_message, "chat_id", None) or (chat.id if chat else None)

    if query_message:
        try:
            await query_message.delete()
        except Exception:
            pass

    if chat_id is None:
        await query.answer("Unable to send collection right now.", show_alert=True)
        return

    try:
        message = await context.bot.send_photo(
            chat_id=chat_id,
            photo=media,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=reply_to_message_id,
        )
        await save_card_file_id_from_message(message, card.id)
    except Exception as e:
        logger.warning(
            f"Failed to send photo using file_id for card {card.id}, falling back to base64: {e}"
        )
        try:
            message = await context.bot.send_photo(
                chat_id=chat_id,
                photo=base64.b64decode(card_with_image.image_b64),
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=reply_to_message_id,
            )
            await save_card_file_id_from_message(message, card.id)
        except Exception as fallback_error:
            logger.error(
                f"Failed to send photo even with base64 fallback for card {card.id}: {fallback_error}"
            )
            await query.answer(
                f"Error displaying card {card.id}. Please try again.", show_alert=True
            )
            return

    await query.answer()


@verify_user
async def handle_collection_navigation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle collection navigation (Prev/Next/Close buttons)."""
    query = update.callback_query
    if not query:
        return

    chat = update.effective_chat
    chat_id_filter = None
    if chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        chat_id_filter = str(chat.id)
    if chat and chat.type != ChatType.PRIVATE:
        is_member = await asyncio.to_thread(
            user_service.is_user_in_chat, str(chat.id), user.user_id
        )
        if not is_member:
            await query.answer(
                "You're not enrolled in this chat yet. Use /enroll in this chat to join.",
                show_alert=True,
            )
            return

    callback_data_parts = query.data.split("_")

    # Extract user IDs from callback data - only support new format
    if len(callback_data_parts) < 4:
        await query.answer(
            "Invalid callback format. Please refresh the collection.", show_alert=True
        )
        return

    original_user_id = int(callback_data_parts[2])
    viewed_user_id = int(callback_data_parts[3])

    if user.user_id != original_user_id:
        await query.answer("You can only navigate collections you initiated!", show_alert=True)
        return

    # Handle close action (after user validation)
    if "close" in query.data:
        await query.delete_message()
        await query.answer()
        return

    # Re-fetch the correct user's collection for navigation
    cards = await asyncio.to_thread(
        card_service.get_user_collection, viewed_user_id, chat_id_filter
    )
    if not cards:
        await query.answer("No cards found.", show_alert=True)
        return

    # Update display_username for the viewed user
    resolved_username = await asyncio.to_thread(
        user_service.get_username_for_user_id, viewed_user_id
    )
    display_username = resolved_username or f"user_{viewed_user_id}"
    collection_key = (viewed_user_id, chat_id_filter)

    total_cards = len(cards)
    collection_indices = context.user_data.setdefault("collection_index", {})
    current_index = collection_indices.get(collection_key, 0)

    if current_index >= total_cards or current_index < 0:
        current_index %= total_cards

    if "prev" in query.data:
        current_index = (current_index - 1) % total_cards
    elif "next" in query.data:
        current_index = (current_index + 1) % total_cards
    else:
        await query.answer()
        return

    collection_indices[collection_key] = current_index

    # Get card details
    card_with_image = await asyncio.to_thread(card_service.get_card, cards[current_index].id)
    if not card_with_image:
        await query.answer("Card not found.", show_alert=True)
        return

    card = cards[current_index]
    lock_icon = "🔒 " if card.locked else ""
    card_title = card.title()
    rarity = card.rarity

    caption = COLLECTION_CAPTION.format(
        lock_icon=lock_icon,
        card_id=card.id,
        card_title=card_title,
        rarity=rarity,
        set_name=(card.set_name or "").title(),
        current_index=current_index + 1,
        total_cards=len(cards),
        username=display_username,
    )

    # Build keyboard
    keyboard = []
    if len(cards) > 1:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "Prev", callback_data=f"collection_prev_{user.user_id}_{viewed_user_id}"
                ),
                InlineKeyboardButton(
                    "Next", callback_data=f"collection_next_{user.user_id}_{viewed_user_id}"
                ),
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "Close", callback_data=f"collection_close_{user.user_id}_{viewed_user_id}"
            )
        ]
    )
    reply_markup = InlineKeyboardMarkup(keyboard)

    media = card_with_image.get_media()

    # Update the message
    try:
        message = await query.edit_message_media(
            media=InputMediaPhoto(media=media, caption="Loading..."),
            reply_markup=reply_markup,
        )
        await query.edit_message_caption(
            caption=caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML
        )
        await save_card_file_id_from_message(message, card.id)
    except Exception as e:
        logger.warning(
            f"Failed to edit message media using file_id for card {card.id}, falling back to base64: {e}"
        )
        # Fallback to base64 upload
        try:
            message = await query.edit_message_media(
                media=InputMediaPhoto(
                    media=base64.b64decode(card_with_image.image_b64), caption="Loading..."
                ),
                reply_markup=reply_markup,
            )
            await query.edit_message_caption(
                caption=caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML
            )
            await save_card_file_id_from_message(message, card.id)
        except Exception as fallback_error:
            logger.error(
                f"Failed to edit message media even with base64 fallback for card {card.id}: {fallback_error}"
            )
            await query.answer(
                f"Error displaying card {card.id}. Please try again.", show_alert=True
            )
            return

    await query.answer()


@verify_user
async def handle_collection_dismiss(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle dismissing the collection initial prompt."""
    query = update.callback_query
    if not query:
        return

    # Parse callback data: collection_dismiss_{requester_user_id}
    try:
        _, _, requester_user_id = query.data.split("_", 2)
        requester_user_id = int(requester_user_id)
    except (ValueError, AttributeError):
        await query.answer("Invalid request.", show_alert=True)
        return

    # Verify that the user clicking the button is the one who requested the collection
    if user.user_id != requester_user_id:
        await query.answer("You can only close collections you requested!", show_alert=True)
        return

    # Delete the message
    try:
        await query.delete_message()
    except Exception as e:
        logger.warning(f"Failed to delete collection prompt message: {e}")
        # Fallback to removing buttons
        try:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.answer("Closed.")
        except Exception as fallback_error:
            logger.error(f"Failed to remove buttons from collection prompt: {fallback_error}")
            await query.answer("Could not close the message.", show_alert=True)


async def _get_user_targets_for_stats(
    chat_id: str, is_private_chat: bool, user: User, args: list[str]
) -> list[tuple[str, Optional[int]]]:
    """Get list of target users for stats display."""
    targets = []

    if is_private_chat:
        # In private chat, only show current user's stats
        username = user.username or f"user_{user.user_id}"
        targets.append((username, user.user_id))
    elif args:
        # Specific user requested
        target_username = args[0].lstrip("@")
        target_user_id = await asyncio.to_thread(
            user_service.get_user_id_by_username, target_username
        )

        if target_user_id is None:
            raise ValueError(f"@{target_username} doesn't exist or isn't enrolled yet.")

        is_member = await asyncio.to_thread(user_service.is_user_in_chat, chat_id, target_user_id)
        if not is_member:
            raise ValueError(f"@{target_username} isn't enrolled in this chat.")

        targets.append((target_username, target_user_id))
    else:
        # All users in chat
        chat_scope = None if is_private_chat else chat_id
        usernames = await asyncio.to_thread(card_service.get_all_users_with_cards, chat_scope)

        if not usernames:
            raise ValueError("No users have claimed any cards yet.")

        for username in usernames:
            user_id = await asyncio.to_thread(user_service.get_user_id_by_username, username)
            targets.append((username, user_id))

    return targets


async def _format_user_stats(username: str, user_id: Optional[int], chat_id: str) -> str:
    """Format stats for a single user."""
    user_stats = await asyncio.to_thread(card_service.get_user_stats, username)

    if user_id is not None:
        balance_value = await asyncio.to_thread(claim_service.get_claim_balance, user_id, chat_id)
        point_label = "point" if balance_value == 1 else "points"
        balance_line = f"{balance_value} {point_label}"

        spin_count = await asyncio.to_thread(
            spin_service.get_user_spin_count,
            user_id,
            chat_id,
        )
        spin_label = "spin" if spin_count == 1 else "spins"
        spins_line = f"{spin_count} {spin_label}"
    else:
        balance_line = "unknown (no linked user ID)"
        spins_line = "unknown (no linked user ID)"

    handle_display = f"@{username}" if username else "unknown"

    return (
        f"{handle_display}: {user_stats['owned']} / {user_stats['total']} cards\n"
        f"U: {user_stats['rarities']['Unique']}, "
        f"L: {user_stats['rarities']['Legendary']}, "
        f"E: {user_stats['rarities']['Epic']}, "
        f"R: {user_stats['rarities']['Rare']}, "
        f"C: {user_stats['rarities']['Common']}\n"
        f"Claims: {balance_line}\n"
        f"Spins: {spins_line}"
    )


@verify_user_in_chat
async def stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Display stats for the current chat, optionally filtered to one user."""
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    chat_id = str(chat.id)
    is_private_chat = chat.type == ChatType.PRIVATE

    # Validate arguments
    if is_private_chat and context.args:
        await message.reply_text(
            "In DMs, /stats only supports your own stats.",
            reply_to_message_id=message.message_id,
        )
        return

    if context.args and len(context.args) > 1:
        await message.reply_text(
            "Usage: /stats [@username]",
            reply_to_message_id=message.message_id,
        )
        return

    # Get target users for stats
    try:
        targets = await _get_user_targets_for_stats(chat_id, is_private_chat, user, context.args)
    except ValueError as e:
        await message.reply_text(str(e), reply_to_message_id=message.message_id)
        return

    # Format stats for all targets
    message_parts = []
    for username, user_id in targets:
        user_line = await _format_user_stats(username, user_id, chat_id)
        message_parts.append(user_line)

    response_text = "\n\n".join(message_parts)
    await message.reply_text(response_text, reply_to_message_id=message.message_id)
