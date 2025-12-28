"""
Card-related command handlers.

This module contains handlers for claiming cards, locking/unlocking cards,
refreshing card images, burning cards, recycling cards, and creating unique cards.
"""

import asyncio
import base64
import datetime
import html
import logging
import random
from io import BytesIO
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from config import DEBUG_MODE, MAX_BOT_IMAGE_RETRIES, gemini_util
from handlers.helpers import (
    build_burning_text,
    log_card_generation,
    save_card_file_id_from_message,
)
from settings.constants import (
    CARD_CAPTION_BASE,
    CARD_STATUS_CLAIMED,
    REFRESH_USAGE_MESSAGE,
    REFRESH_DM_RESTRICTED_MESSAGE,
    REFRESH_INVALID_ID_MESSAGE,
    REFRESH_CARD_NOT_FOUND_MESSAGE,
    REFRESH_NOT_YOURS_MESSAGE,
    REFRESH_CHAT_MISMATCH_MESSAGE,
    REFRESH_INSUFFICIENT_BALANCE_MESSAGE,
    REFRESH_CONFIRM_MESSAGE,
    REFRESH_CANCELLED_MESSAGE,
    REFRESH_ALREADY_RUNNING_MESSAGE,
    REFRESH_PROCESSING_MESSAGE,
    REFRESH_FAILURE_MESSAGE,
    REFRESH_SUCCESS_MESSAGE,
    REFRESH_OPTIONS_READY_MESSAGE,
    get_refresh_cost,
    get_lock_cost,
    # Burn constants
    BURN_USAGE_MESSAGE,
    BURN_DM_RESTRICTED_MESSAGE,
    BURN_INVALID_ID_MESSAGE,
    BURN_CARD_NOT_FOUND_MESSAGE,
    BURN_NOT_YOURS_MESSAGE,
    BURN_CHAT_MISMATCH_MESSAGE,
    BURN_CONFIRM_MESSAGE,
    BURN_CANCELLED_MESSAGE,
    BURN_ALREADY_RUNNING_MESSAGE,
    BURN_PROCESSING_MESSAGE,
    BURN_FAILURE_MESSAGE,
    BURN_FAILURE_SPINS_MESSAGE,
    BURN_SUCCESS_MESSAGE,
    get_spin_reward,
    # Recycle constants
    RECYCLE_ALLOWED_RARITIES,
    RECYCLE_UPGRADE_MAP,
    RECYCLE_USAGE_MESSAGE,
    RECYCLE_DM_RESTRICTED_MESSAGE,
    RECYCLE_CONFIRM_MESSAGE,
    RECYCLE_INSUFFICIENT_CARDS_MESSAGE,
    RECYCLE_ALREADY_RUNNING_MESSAGE,
    RECYCLE_NOT_YOURS_MESSAGE,
    RECYCLE_UNKNOWN_RARITY_MESSAGE,
    RECYCLE_FAILURE_NOT_ENOUGH_CARDS,
    RECYCLE_FAILURE_NO_PROFILE,
    RECYCLE_FAILURE_IMAGE,
    RECYCLE_FAILURE_UNEXPECTED,
    RECYCLE_RESULT_APPENDIX,
    get_recycle_required_cards,
    # Create unique constants
    CREATE_USAGE_MESSAGE,
    CREATE_DM_RESTRICTED_MESSAGE,
    CREATE_CONFIRM_MESSAGE,
    CREATE_WARNING_EXISTING_MODIFIER,
    CREATE_INSUFFICIENT_CARDS_MESSAGE,
    CREATE_ALREADY_RUNNING_MESSAGE,
    CREATE_NOT_YOURS_MESSAGE,
    CREATE_FAILURE_NO_PROFILE,
    CREATE_FAILURE_UNEXPECTED,
    CREATE_CANCELLED_MESSAGE,
    UNIQUE_ADDENDUM,
)
from utils import rolling
from utils.services import card_service, user_service, claim_service, spin_service
from utils.schemas import User, Card
from utils.decorators import verify_user, verify_user_in_chat
from utils.rolled_card import ClaimStatus, RolledCardManager

logger = logging.getLogger(__name__)


@verify_user_in_chat
async def claim_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle claim button click."""
    query = update.callback_query
    data = query.data
    roll_id = int(data.split("_")[1])
    chat = update.effective_chat
    chat_id = str(chat.id) if chat else None

    # Use RolledCardManager to handle the claim logic
    rolled_card_manager = RolledCardManager(roll_id)

    card = rolled_card_manager.card
    if card is None:
        await query.answer("Card not found!", show_alert=True)
        return

    if rolled_card_manager.is_being_rerolled():
        await query.answer("The card is being rerolled, please wait.", show_alert=True)
        return

    claim_result = await asyncio.to_thread(
        RolledCardManager.claim_card,
        rolled_card_manager,
        user.username,
        user.user_id,
        chat_id,
    )

    cost_to_spend = claim_result.cost if claim_result.cost is not None else 1

    if claim_result.status is ClaimStatus.INSUFFICIENT_BALANCE:
        message = f"Not enough claim points!\n\n" f"Cost: {cost_to_spend}"
        if claim_result.balance is not None:
            message += f"\n\nBalance: {claim_result.balance}"
        await query.answer(message, show_alert=True)
        return

    card = rolled_card_manager.card
    card_title = card.title()

    spent_line = f"Spent: {cost_to_spend} claim point{'s' if cost_to_spend != 1 else ''}"

    def _build_claim_message(balance: Optional[int]) -> str:
        success_message = f"Card {card_title} claimed!\n\n{spent_line}"
        if balance is not None:
            success_message += f"\n\nRemaining balance: {balance}."
        return success_message

    if claim_result.status is ClaimStatus.SUCCESS:
        await query.answer(_build_claim_message(claim_result.balance), show_alert=True)
    elif claim_result.status is ClaimStatus.ALREADY_OWNED_BY_USER:
        # Show success message with current balance for user's own card
        remaining_balance = claim_result.balance
        if remaining_balance is None and chat_id and user.user_id:
            remaining_balance = await asyncio.to_thread(
                claim_service.get_claim_balance, user.user_id, chat_id
            )
        await query.answer(_build_claim_message(remaining_balance), show_alert=True)
    elif claim_result.status is ClaimStatus.INSUFFICIENT_BALANCE:
        await query.answer("Insufficient claim points!", show_alert=True)
    else:
        # Card already claimed by someone else
        # Fetch fresh card to get the actual owner
        fresh_card = rolled_card_manager.card
        owner = fresh_card.owner if fresh_card else "someone"
        await query.answer(f"Too late! Already claimed by @{owner}.", show_alert=True)

    # Update the message with new caption and keyboard
    caption = rolled_card_manager.generate_caption()
    reply_markup = rolled_card_manager.generate_keyboard()

    try:
        await query.edit_message_caption(
            caption=caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML
        )
    except Exception:
        # Silently ignore if message content is identical (Telegram BadRequest)
        pass


@verify_user_in_chat
async def handle_lock(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle lock button click to prevent rerolling."""
    query = update.callback_query

    data_parts = query.data.split("_")
    if len(data_parts) < 2:
        await query.answer("Invalid lock request.", show_alert=True)
        return

    roll_id = int(data_parts[1])

    # Use RolledCardManager to handle lock logic
    rolled_card_manager = RolledCardManager(roll_id)

    if not rolled_card_manager.is_valid():
        await query.answer("Card not found!", show_alert=True)
        return

    # Check if the card has been claimed
    if not rolled_card_manager.is_claimed():
        await query.answer("Card must be claimed before it can be locked!", show_alert=True)
        return

    card = rolled_card_manager.card
    if card is None:
        await query.answer("Card not found!", show_alert=True)
        return

    # Check if the person trying to lock is the owner of the card
    if not rolled_card_manager.can_user_lock(user.user_id, user.username):
        await query.answer("Only the owner of the card can lock it!", show_alert=True)
        return

    chat = update.effective_chat
    chat_id = str(chat.id) if chat else None

    try:
        lock_result = await asyncio.to_thread(
            RolledCardManager.lock_card,
            rolled_card_manager,
            user.user_id,
            chat_id,
        )
    except ValueError as exc:
        logger.error("Lock failed: %s", exc)
        await query.answer("Unable to lock this card right now.", show_alert=True)
        return

    if not lock_result.success:
        message = f"Not enough claim points!\n\nCost: {lock_result.cost}"
        if lock_result.current_balance is not None:
            message += f"\n\nBalance: {lock_result.current_balance}"
        await query.answer(message, show_alert=True)
        return

    if lock_result.cost > 0:
        message = (
            "Card locked from re-rolling!\n\n"
            f"Spent: {lock_result.cost} claim point"
            f"{'s' if lock_result.cost != 1 else ''}"
        )
        if lock_result.remaining_balance is not None:
            message += f"\n\nBalance: {lock_result.remaining_balance}"
        await query.answer(message, show_alert=True)
    else:
        # Original roller - no claim point needed since they can't reroll their own claimed card anyway
        await query.answer("Card locked from re-rolling!", show_alert=True)

    # Set the card as locked
    # Update the message caption and remove all buttons when locked
    caption = rolled_card_manager.generate_caption()

    try:
        await query.edit_message_caption(
            caption=caption, reply_markup=None, parse_mode=ParseMode.HTML
        )
    except Exception:
        # Silently ignore if message content is identical
        pass


@verify_user_in_chat
async def lock_card_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Initiate lock/unlock for a card by ID."""
    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type == ChatType.PRIVATE and not DEBUG_MODE:
        await message.reply_text("Only allowed to lock cards in the group chat.")
        return

    from settings.constants import LOCK_USAGE_MESSAGE

    if len(context.args) != 1:
        await message.reply_text(LOCK_USAGE_MESSAGE)
        return

    try:
        card_id = int(context.args[0])
    except ValueError:
        await message.reply_text("Card ID must be a number.")
        return

    card = await asyncio.to_thread(card_service.get_card, card_id)

    if not card:
        await message.reply_text("Card ID is invalid.")
        return

    # Check if the user owns this card
    if card.owner != user.username:
        await message.reply_text(
            f"You do not own card <b>{card.title()}</b>.", parse_mode=ParseMode.HTML
        )
        return

    # Check current lock status and prepare appropriate message
    lock_cost = get_lock_cost(card.rarity)

    if card.locked:
        # Card is already locked - offer to unlock (no refund)
        if lock_cost > 0:
            refund_label = "Claim point" if lock_cost == 1 else "Claim points"
            prompt_text = (
                f"Unlock <b>{card.title()}</b>? {refund_label} will <b>not</b> be refunded."
            )
        else:
            prompt_text = f"Unlock <b>{card.title()}</b>?"
    else:
        # Card is not locked - offer to lock (costs configured claim points)
        # Balance will be checked when user confirms
        if lock_cost > 0:
            points_label = "claim point" if lock_cost == 1 else "claim points"
            prompt_text = f"Consume {lock_cost} {points_label} to lock <b>{card.title()}</b>?"
        else:
            prompt_text = f"Lock <b>{card.title()}</b>?"

    keyboard = [
        [
            InlineKeyboardButton("Yes", callback_data=f"lockcard_yes_{card_id}_{user.user_id}"),
            InlineKeyboardButton("No", callback_data=f"lockcard_no_{card_id}_{user.user_id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(
        prompt_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
        reply_to_message_id=message.message_id,
    )


@verify_user_in_chat
async def handle_lock_card_confirm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle confirmation (yes) for locking/unlocking a card."""
    query = update.callback_query
    if not query:
        return

    data_parts = query.data.split("_")
    if len(data_parts) < 4:
        await query.answer("Invalid request.", show_alert=True)
        return

    _, action, card_id_str, target_user_id_str = data_parts[:4]

    try:
        card_id = int(card_id_str)
        target_user_id = int(target_user_id_str)
    except ValueError:
        await query.answer("Invalid card or user ID.", show_alert=True)
        return

    # Verify the user clicking is the same as the one who initiated
    if user.user_id != target_user_id:
        await query.answer("This action is not for you!")
        return

    if action == "no":
        await query.answer("Lock action cancelled.")
        try:
            await query.message.delete()
        except Exception:
            try:
                await query.edit_message_text("Lock action cancelled.")
            except Exception:
                pass
        return

    if action != "yes":
        await query.answer()
        return

    # Get the card and verify ownership
    card = await asyncio.to_thread(card_service.get_card, card_id)
    if not card:
        await query.answer("Card not found!", show_alert=True)
        try:
            await query.edit_message_text("Card not found.")
        except Exception:
            pass
        return

    if card.owner != user.username:
        await query.answer("You don't own this card!", show_alert=True)
        try:
            await query.edit_message_text("You don't own this card.")
        except Exception:
            pass
        return

    chat = update.effective_chat
    if not chat:
        await query.answer("Chat context unavailable.", show_alert=True)
        return

    chat_id = str(chat.id)
    card_title = card.title()

    lock_cost = get_lock_cost(card.rarity)

    if card.locked:
        # Unlock the card (no cost)
        await asyncio.to_thread(card_service.set_card_locked, card_id, False)
        response_text = f"🔓 <b>{card_title}</b> unlocked!"
        await query.answer(f"{card_title} unlocked!", show_alert=False)
    else:
        # Lock the card (consumes configured claim points)
        # First check if user has enough balance
        current_balance = await asyncio.to_thread(
            claim_service.get_claim_balance, user.user_id, chat_id
        )

        if current_balance < lock_cost:
            # Insufficient balance
            await query.answer(
                ("Not enough claim points!\n\n" f"Cost: {lock_cost}\nBalance: {current_balance}"),
                show_alert=True,
            )
            try:
                await query.edit_message_text(
                    (
                        f"Not enough claim points to lock <b>{card_title}</b>!\n\n"
                        f"Cost: {lock_cost}\nBalance: {current_balance}"
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            return

        # Now try to consume the claim point
        remaining_balance = await asyncio.to_thread(
            claim_service.reduce_claim_points, user.user_id, chat_id, lock_cost
        )

        if remaining_balance is None:
            # This shouldn't happen since we checked above, but handle it anyway
            current_balance = await asyncio.to_thread(
                claim_service.get_claim_balance, user.user_id, chat_id
            )
            await query.answer(
                ("Not enough claim points!\n\n" f"Cost: {lock_cost}\nBalance: {current_balance}"),
                show_alert=True,
            )
            try:
                await query.edit_message_text(
                    (
                        f"Not enough claim points to lock <b>{card_title}</b>!\n\n"
                        f"Cost: {lock_cost}\nBalance: {current_balance}"
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            return

        # Lock the card
        await asyncio.to_thread(card_service.set_card_locked, card_id, True)
        response_text = (
            f"🔒 <b>{card_title}</b> locked!\n\n"
            + (f"Cost: {lock_cost}\n" if lock_cost > 0 else "")
            + f"Remaining balance: {remaining_balance}"
        )
        plain_response = (
            f"{card_title} locked!\n\n"
            + (f"Cost: {lock_cost}\n" if lock_cost > 0 else "")
            + f"Remaining balance: {remaining_balance}"
        )
        await query.answer(plain_response, show_alert=True)

    try:
        await query.edit_message_text(response_text, parse_mode=ParseMode.HTML)
    except Exception:
        pass


@verify_user_in_chat
async def refresh(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Refresh a card's image for claim points."""
    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type == ChatType.PRIVATE and not DEBUG_MODE:
        await message.reply_text(
            REFRESH_DM_RESTRICTED_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    if not context.args:
        await message.reply_text(
            REFRESH_USAGE_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    card_id_arg = context.args[0]
    try:
        card_id = int(card_id_arg)
    except ValueError:
        await message.reply_text(
            REFRESH_INVALID_ID_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    card = await asyncio.to_thread(card_service.get_card, card_id)
    if not card:
        await message.reply_text(
            REFRESH_CARD_NOT_FOUND_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    chat_id_str = str(chat.id)
    if not card.chat_id or card.chat_id != chat_id_str:
        await message.reply_text(
            REFRESH_CHAT_MISMATCH_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    username = user.username
    if not username:
        return

    owns_card = card.user_id == user.user_id or (username and card.owner == username)
    if not owns_card:
        await message.reply_text(
            REFRESH_NOT_YOURS_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    # Check claim balance
    refresh_cost = get_refresh_cost(card.rarity)
    balance = await asyncio.to_thread(claim_service.get_claim_balance, user.user_id, chat_id_str)
    if balance < refresh_cost:
        await message.reply_text(
            REFRESH_INSUFFICIENT_BALANCE_MESSAGE.format(balance=balance, cost=refresh_cost),
            parse_mode=ParseMode.HTML,
            reply_to_message_id=message.message_id,
        )
        return

    card_title = card.title(include_id=True, include_rarity=True)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Refresh!", callback_data=f"refresh_yes_{card_id}_{user.user_id}"
                ),
                InlineKeyboardButton(
                    "Cancel", callback_data=f"refresh_cancel_{card_id}_{user.user_id}"
                ),
            ]
        ]
    )

    # Send the card image with the confirmation message
    card_media = card.get_media()
    await message.reply_photo(
        photo=card_media,
        caption=REFRESH_CONFIRM_MESSAGE.format(
            card_title=card_title,
            balance=balance,
            cost=refresh_cost,
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        reply_to_message_id=message.message_id,
    )


def _build_refresh_navigation_keyboard(
    card_id: int,
    user_id: int,
    current_option: int,
    total_options: int,
) -> InlineKeyboardMarkup:
    """Build navigation keyboard for refresh options with wrap-around."""
    buttons = []

    # Navigation buttons - always show both on the same row with wrap-around
    prev_option = current_option - 1 if current_option > 1 else total_options
    next_option = current_option + 1 if current_option < total_options else 1

    buttons.append(
        [
            InlineKeyboardButton(
                "Prev", callback_data=f"refresh_nav_{prev_option}_{card_id}_{user_id}"
            ),
            InlineKeyboardButton(
                "Next", callback_data=f"refresh_nav_{next_option}_{card_id}_{user_id}"
            ),
        ]
    )

    # Select button on its own row
    buttons.append(
        [
            InlineKeyboardButton(
                "Select", callback_data=f"refresh_pick_{current_option}_{card_id}_{user_id}"
            )
        ]
    )

    return InlineKeyboardMarkup(buttons)


async def _handle_refresh_cancel(
    query,
    card_id: int,
) -> None:
    """Handle refresh cancellation from confirmation screen."""
    card = await asyncio.to_thread(card_service.get_card, card_id)
    if card:
        card_title = card.title(include_id=True, include_rarity=True)
        cancel_msg = REFRESH_CANCELLED_MESSAGE.format(card_title=card_title)
    else:
        cancel_msg = "Refresh cancelled."
    try:
        await query.edit_message_caption(
            caption=cancel_msg, parse_mode=ParseMode.HTML, reply_markup=None
        )
    except Exception:
        pass
    await query.answer()


async def _handle_refresh_nav(
    query,
    user: User,
    card_id: int,
    option_index: int,
    refresh_sessions: dict,
    session_key: str,
) -> None:
    """Handle navigation between refresh options."""
    session = refresh_sessions.get(session_key)
    if not session:
        await query.answer("This refresh is no longer active.", show_alert=True)
        return

    options: list[str] = session["options"]
    if option_index < 1 or option_index > len(options):
        await query.answer("Invalid option.", show_alert=True)
        return

    # Get the card info for caption
    card = await asyncio.to_thread(card_service.get_card, card_id)
    card_title = card.title(include_id=True, include_rarity=True) if card else f"Card {card_id}"
    remaining_balance = session["remaining_balance"]

    options_caption = REFRESH_OPTIONS_READY_MESSAGE.format(
        card_title=card_title,
        remaining_balance=remaining_balance,
    )

    # Label option 1 as "Original", others as regular options
    if option_index == 1:
        option_label = f"<b>Option {option_index} of {len(options)} (Original)</b>"
    else:
        option_label = f"<b>Option {option_index} of {len(options)}</b>"

    caption = f"{options_caption}\n\n{option_label}"

    # Update to show the selected option
    keyboard = _build_refresh_navigation_keyboard(card_id, user.user_id, option_index, len(options))

    option_b64 = options[option_index - 1]
    image_bytes = base64.b64decode(option_b64)
    image_file = BytesIO(image_bytes)
    image_file.name = f"refresh_option_{option_index}.jpg"

    try:
        await query.edit_message_media(
            media=InputMediaPhoto(
                media=image_file,
                caption=caption,
                parse_mode=ParseMode.HTML,
            ),
            reply_markup=keyboard,
        )
        await query.answer()
    except Exception as exc:
        logger.warning("Failed to navigate to option %s: %s", option_index, exc)
        await query.answer("Failed to load option.", show_alert=True)


async def _handle_refresh_pick(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
    card_id: int,
    option_index: int,
    refresh_sessions: dict,
    session_key: str,
) -> None:
    """Handle user selecting a refresh option."""
    session = refresh_sessions.get(session_key)
    if not session or option_index is None:
        await query.answer("This refresh is no longer active.", show_alert=True)
        return

    selection_idx = option_index - 1
    options: list[str] = session["options"]
    if selection_idx < 0 or selection_idx >= len(options):
        await query.answer("Invalid option.", show_alert=True)
        return

    card = await asyncio.to_thread(card_service.get_card, card_id)
    card_title = card.title(include_id=True, include_rarity=True) if card else f"Card {card_id}"
    chat_id_for_balance = session["chat_id"]

    # If user selected the original image (option 1), keep the original without updating
    if option_index == 1:
        latest_balance = await asyncio.to_thread(
            claim_service.get_claim_balance, user.user_id, chat_id_for_balance
        )
        success_message = (
            f"<b>{card_title}</b>\n\nKept original image.\n\nBalance: {latest_balance}"
        )
    else:
        # Update the card with the new image
        chosen_image_b64 = options[selection_idx]
        await asyncio.to_thread(card_service.update_card_image, card_id, chosen_image_b64)

        latest_balance = await asyncio.to_thread(
            claim_service.get_claim_balance, user.user_id, chat_id_for_balance
        )
        success_message = REFRESH_SUCCESS_MESSAGE.format(
            card_title=card_title,
            selection=option_index,
            remaining_balance=latest_balance,
        )

    # Get the selected image for display
    chosen_image_b64 = options[selection_idx]
    image_bytes = base64.b64decode(chosen_image_b64)
    image_file = BytesIO(image_bytes)
    image_file.name = f"refresh_option_{option_index}.jpg"

    try:
        edited_message = await query.edit_message_media(
            media=InputMediaPhoto(
                media=image_file,
                caption=success_message,
                parse_mode=ParseMode.HTML,
            ),
            reply_markup=None,
        )
        await save_card_file_id_from_message(edited_message, card_id)
    except Exception as exc:
        logger.warning("Failed to update message with selected option: %s", exc)
        await query.edit_message_caption(
            caption=success_message,
            parse_mode=ParseMode.HTML,
            reply_markup=None,
        )

    logger.info(
        "User %s selected option %s for card %s refresh.",
        user.user_id,
        option_index,
        card_id,
    )

    refresh_sessions.pop(session_key, None)
    await query.answer(f"Saved option {option_index}!")


async def _validate_refresh_ownership(
    card: Card,
    user: User,
) -> bool:
    """Validate that the user owns the card."""
    username = user.username
    if not username:
        return False

    return card.user_id == user.user_id or (username and card.owner == username)


async def _generate_refresh_options(
    card: Card,
    gemini_util,
    max_retries: int,
) -> tuple[str, str]:
    """Generate two refresh image options."""
    option1_b64 = await asyncio.to_thread(
        rolling.regenerate_card_image,
        card,
        gemini_util,
        max_retries=max_retries,
        refresh_attempt=2,
    )
    option2_b64 = await asyncio.to_thread(
        rolling.regenerate_card_image,
        card,
        gemini_util,
        max_retries=max_retries,
        refresh_attempt=3,
    )
    return option1_b64, option2_b64


async def _update_to_refresh_options(
    query,
    card_id: int,
    user_id: int,
    card_title: str,
    remaining_balance: int,
    original_image_b64: str,
):
    """Update the confirmation message to show the original image as option 1."""
    num_options = 3  # Original + 2 new options
    keyboard = _build_refresh_navigation_keyboard(card_id, user_id, 1, num_options)

    options_caption = REFRESH_OPTIONS_READY_MESSAGE.format(
        card_title=card_title,
        remaining_balance=remaining_balance,
    )
    caption = f"{options_caption}\n\n<b>Option 1 of {num_options} (Original)</b>"

    original_photo = BytesIO(base64.b64decode(original_image_b64))
    original_photo.name = "refresh_option_1_original.jpg"

    # Update the existing message with the original image as option 1
    await query.edit_message_media(
        media=InputMediaPhoto(
            media=original_photo,
            caption=caption,
            parse_mode=ParseMode.HTML,
        ),
        reply_markup=keyboard,
    )


async def _handle_refresh_confirm(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
    card_id: int,
    chat_id_str: Optional[str],
    refresh_sessions: dict,
    session_key: str,
    refreshing_users: set,
) -> None:
    """Handle the confirmation 'yes' action to start refresh process."""
    try:
        card = await asyncio.to_thread(card_service.get_card, card_id)
        if not card:
            await query.answer(REFRESH_CARD_NOT_FOUND_MESSAGE, show_alert=True)
            return

        if not await _validate_refresh_ownership(card, user):
            await query.answer(REFRESH_NOT_YOURS_MESSAGE, show_alert=True)
            return

        refresh_cost = get_refresh_cost(card.rarity)
        active_chat_id = card.chat_id or chat_id_str
        balance = await asyncio.to_thread(
            claim_service.get_claim_balance, user.user_id, active_chat_id
        )

        if balance < refresh_cost:
            await query.answer(
                REFRESH_INSUFFICIENT_BALANCE_MESSAGE.format(balance=balance, cost=refresh_cost),
                show_alert=True,
            )
            return

        remaining_balance = await asyncio.to_thread(
            claim_service.reduce_claim_points, user.user_id, active_chat_id, refresh_cost
        )

        if remaining_balance is None:
            await query.answer(
                REFRESH_INSUFFICIENT_BALANCE_MESSAGE.format(balance=balance, cost=refresh_cost),
                show_alert=True,
            )
            return

        await query.answer()
        card_title = card.title(include_id=True, include_rarity=True)
        processing_msg = REFRESH_PROCESSING_MESSAGE.format(card_title=card_title)
        try:
            await query.edit_message_caption(
                caption=processing_msg, parse_mode=ParseMode.HTML, reply_markup=None
            )
        except Exception:
            pass

        # Generate two image options
        try:
            option1_b64, option2_b64 = await _generate_refresh_options(
                card, gemini_util, MAX_BOT_IMAGE_RETRIES
            )
        except (
            rolling.ImageGenerationError,
            rolling.InvalidSourceError,
            rolling.NoEligibleUserError,
        ) as exc:
            logger.warning("Image regeneration failed for card %s: %s", card_id, exc)
            await asyncio.to_thread(
                claim_service.increment_claim_balance, user.user_id, active_chat_id, refresh_cost
            )
            failure_msg = REFRESH_FAILURE_MESSAGE.format(card_title=card_title)
            await query.answer(
                "Refresh failed. Image generation is unavailable right now.", show_alert=True
            )
            try:
                await query.edit_message_caption(
                    caption=failure_msg, parse_mode=ParseMode.HTML, reply_markup=None
                )
            except Exception:
                pass
            return

        # Get the original image to use as option 1
        original_image_b64 = card.image_b64

        # Update the confirmation message to show the original image as option 1
        try:
            await _update_to_refresh_options(
                query,
                card_id,
                user.user_id,
                card_title,
                remaining_balance,
                original_image_b64,
            )
        except Exception as exc:
            logger.warning("Failed to show refresh options for card %s: %s", card_id, exc)
            await asyncio.to_thread(
                claim_service.increment_claim_balance, user.user_id, active_chat_id, refresh_cost
            )
            await query.answer(
                "Refresh failed. Image generation is unavailable right now.", show_alert=True
            )
            failure_msg = REFRESH_FAILURE_MESSAGE.format(card_title=card_title)
            try:
                await query.edit_message_caption(
                    caption=failure_msg, parse_mode=ParseMode.HTML, reply_markup=None
                )
            except Exception:
                pass
            return

        # Store session data with original image as option 1, new images as options 2 and 3
        refresh_sessions[session_key] = {
            "options": [original_image_b64, option1_b64, option2_b64],
            "cost": refresh_cost,
            "remaining_balance": remaining_balance,
            "chat_id": active_chat_id,
        }

    except Exception as exc:
        logger.exception("Unexpected error during refresh for card %s: %s", card_id, exc)
        await query.answer("Refresh failed due to an unexpected error.", show_alert=True)
        try:
            error_card = await asyncio.to_thread(card_service.get_card, card_id)
            if error_card:
                error_title = error_card.title(include_id=True, include_rarity=True)
                error_msg = REFRESH_FAILURE_MESSAGE.format(card_title=error_title)
            else:
                error_msg = "Refresh failed. Image generation is unavailable right now."
            await query.edit_message_caption(
                caption=error_msg, parse_mode=ParseMode.HTML, reply_markup=None
            )
        except Exception:
            pass
    finally:
        refreshing_users.discard(user.user_id)


@verify_user_in_chat
async def handle_refresh_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle refresh flow: confirmation, image generation, selection, and cancellation."""
    query = update.callback_query
    if not query:
        return

    data_parts = query.data.split("_")
    if len(data_parts) < 4:
        await query.answer("Invalid refresh data.")
        return

    action = data_parts[1]
    option_index: Optional[int] = None

    # Parse callback data based on action
    if action in ("pick", "nav"):
        if len(data_parts) < 5:
            await query.answer("Invalid refresh data.")
            return
        try:
            option_index = int(data_parts[2])
        except ValueError:
            await query.answer("Invalid option.")
            return
        card_id_str = data_parts[3]
        target_user_id_str = data_parts[4]
    else:
        card_id_str = data_parts[2]
        target_user_id_str = data_parts[3]

    try:
        card_id = int(card_id_str)
        target_user_id = int(target_user_id_str)
    except ValueError:
        await query.answer("Invalid refresh data.")
        return

    # Verify user authorization
    if target_user_id != user.user_id:
        await query.answer("This refresh prompt isn't for you!")
        return

    refresh_sessions = context.bot_data.setdefault("refresh_sessions", {})
    session_key = f"{card_id}:{user.user_id}"

    # Route to appropriate handler based on action
    if action == "cancel":
        await _handle_refresh_cancel(query, card_id)
        return

    if action == "nav":
        await _handle_refresh_nav(query, user, card_id, option_index, refresh_sessions, session_key)
        return

    if action == "pick":
        await _handle_refresh_pick(
            query, context, user, card_id, option_index, refresh_sessions, session_key
        )
        return

    if action == "yes":
        refreshing_users = context.bot_data.setdefault("refreshing_users", set())
        if user.user_id in refreshing_users:
            await query.answer(REFRESH_ALREADY_RUNNING_MESSAGE)
            return

        refreshing_users.add(user.user_id)
        chat = update.effective_chat
        chat_id_str = str(chat.id) if chat else None

        await _handle_refresh_confirm(
            query,
            context,
            user,
            card_id,
            chat_id_str,
            refresh_sessions,
            session_key,
            refreshing_users,
        )
        return

    await query.answer("Unknown action.")


# =============================================================================
# Burn Card Handlers
# =============================================================================


@verify_user_in_chat
async def burn(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Burn a card for spins."""
    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type == ChatType.PRIVATE and not DEBUG_MODE:
        await message.reply_text(
            BURN_DM_RESTRICTED_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    if not context.args:
        await message.reply_text(
            BURN_USAGE_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    card_id_arg = context.args[0]
    try:
        card_id = int(card_id_arg)
    except ValueError:
        await message.reply_text(
            BURN_INVALID_ID_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    card = await asyncio.to_thread(card_service.get_card, card_id)
    if not card:
        await message.reply_text(
            BURN_CARD_NOT_FOUND_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    chat_id_str = str(chat.id)
    if not card.chat_id or card.chat_id != chat_id_str:
        await message.reply_text(
            BURN_CHAT_MISMATCH_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    username = user.username
    if not username:
        username = await asyncio.to_thread(user_service.get_username_for_user_id, user.user_id)

    owns_card = card.user_id == user.user_id or (username and card.owner == username)
    if not owns_card:
        await message.reply_text(
            BURN_NOT_YOURS_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    spin_reward = get_spin_reward(card.rarity)
    if spin_reward <= 0:
        logger.error("No spin reward configured for rarity %s", card.rarity)
        await message.reply_text(
            BURN_FAILURE_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    card_title = card.title()
    escaped_title = html.escape(card_title)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Burn it!", callback_data=f"burn_yes_{card_id}_{user.user_id}"
                ),
                InlineKeyboardButton(
                    "Cancel", callback_data=f"burn_cancel_{card_id}_{user.user_id}"
                ),
            ]
        ]
    )

    await message.reply_text(
        BURN_CONFIRM_MESSAGE.format(
            card_id=card.id,
            rarity=card.rarity,
            card_title=escaped_title,
            spin_reward=spin_reward,
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        reply_to_message_id=message.message_id,
    )


@verify_user_in_chat
async def handle_burn_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle burn confirmation callback."""
    query = update.callback_query
    if not query:
        return

    data_parts = query.data.split("_")
    if len(data_parts) < 4:
        await query.answer()
        return

    _, action, card_id_str, target_user_id_str = data_parts[:4]

    try:
        card_id = int(card_id_str)
        target_user_id = int(target_user_id_str)
    except ValueError:
        await query.answer(BURN_FAILURE_MESSAGE, show_alert=True)
        return

    if target_user_id != user.user_id:
        await query.answer(BURN_NOT_YOURS_MESSAGE)
        return

    if action == "cancel":
        await query.answer(BURN_CANCELLED_MESSAGE)
        try:
            await query.message.delete()
        except Exception:
            try:
                await query.edit_message_text(BURN_CANCELLED_MESSAGE)
            except Exception:
                pass
        return

    if action != "yes":
        await query.answer()
        return

    burning_users = context.bot_data.setdefault("burning_users", set())
    if user.user_id in burning_users:
        await query.answer(BURN_ALREADY_RUNNING_MESSAGE, show_alert=True)
        return

    burning_users.add(user.user_id)

    chat = update.effective_chat
    chat_id_str = str(chat.id) if chat else None

    try:
        if not chat_id_str:
            await query.answer(BURN_FAILURE_MESSAGE, show_alert=True)
            return

        card = await asyncio.to_thread(card_service.get_card, card_id)
        if not card:
            await query.answer(BURN_CARD_NOT_FOUND_MESSAGE, show_alert=True)
            try:
                await query.edit_message_text(BURN_CARD_NOT_FOUND_MESSAGE)
            except Exception:
                pass
            return

        if not card.chat_id or card.chat_id != chat_id_str:
            await query.answer(BURN_CHAT_MISMATCH_MESSAGE, show_alert=True)
            try:
                await query.edit_message_text(BURN_CHAT_MISMATCH_MESSAGE)
            except Exception:
                pass
            return

        username = user.username
        if not username:
            username = await asyncio.to_thread(user_service.get_username_for_user_id, user.user_id)

        owns_card = card.user_id == user.user_id or (username and card.owner == username)
        if not owns_card:
            await query.answer(BURN_NOT_YOURS_MESSAGE, show_alert=True)
            try:
                await query.edit_message_text(BURN_NOT_YOURS_MESSAGE)
            except Exception:
                pass
            return

        spin_reward = get_spin_reward(card.rarity)
        if spin_reward <= 0:
            logger.error("No spin reward configured for rarity %s", card.rarity)
            await query.answer(BURN_FAILURE_MESSAGE, show_alert=True)
            try:
                await query.edit_message_text(BURN_FAILURE_MESSAGE)
            except Exception:
                pass
            return

        card_title = card.title()
        escaped_title = html.escape(card_title)

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        try:
            await query.edit_message_text(BURN_PROCESSING_MESSAGE)
        except Exception:
            pass

        success = await asyncio.to_thread(card_service.delete_card, card_id)
        if not success:
            await query.answer(BURN_FAILURE_MESSAGE, show_alert=True)
            try:
                await query.edit_message_text(BURN_FAILURE_MESSAGE)
            except Exception:
                pass
            return

        new_spin_total = await asyncio.to_thread(
            spin_service.increment_user_spins, user.user_id, chat_id_str, spin_reward
        )

        if new_spin_total is None:
            logger.error(
                "Card %s burned but failed to award spins to user %s in chat %s",
                card_id,
                user.user_id,
                chat_id_str,
            )
            await query.answer(BURN_FAILURE_SPINS_MESSAGE, show_alert=True)
            try:
                await query.edit_message_text(BURN_FAILURE_SPINS_MESSAGE)
            except Exception:
                pass
            return

        header = f"<b><s>🔥[{card_id}] {card.rarity} {escaped_title}🔥</s></b>"
        success_block = BURN_SUCCESS_MESSAGE.format(
            spin_reward=spin_reward,
            new_spin_total=new_spin_total,
        )

        final_text = f"{header}\n\n{success_block}"

        await query.edit_message_text(
            final_text,
            parse_mode=ParseMode.HTML,
        )
        await query.answer("Burn complete!")

        logger.info(
            "User %s (%s) burned card %s in chat %s for %s spins",
            username or f"user_{user.user_id}",
            user.user_id,
            card_id,
            chat_id_str,
            spin_reward,
        )
    except Exception as exc:
        logger.exception("Unexpected error during burn for card %s: %s", card_id, exc)
        await query.answer(BURN_FAILURE_MESSAGE, show_alert=True)
        try:
            await query.edit_message_text(BURN_FAILURE_MESSAGE)
        except Exception:
            pass
    finally:
        burning_users.discard(user.user_id)


# =============================================================================
# Create Unique Card Handlers
# =============================================================================


@verify_user_in_chat
async def create_unique_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Create a unique card by recycling legendary cards."""
    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type == ChatType.PRIVATE and not DEBUG_MODE:
        await message.reply_text(
            CREATE_DM_RESTRICTED_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    if not context.args or len(context.args) < 2:
        cost = rolling.RARITIES["Unique"]["recycle_cost"]
        await message.reply_text(
            CREATE_USAGE_MESSAGE.format(cost=cost),
            parse_mode=ParseMode.HTML,
            reply_to_message_id=message.message_id,
        )
        return

    # Parse arguments: Modifier Name (Name is always the last word)
    full_text = " ".join(context.args)
    chat_id_str = str(chat.id)

    name = context.args[-1]
    modifier_raw = " ".join(context.args[:-1])
    modifier = (
        modifier_raw[0].upper() + modifier_raw[1:] if modifier_raw else ""
    )  # Capitalize first letter

    if len(modifier) > 15:
        await message.reply_text(
            "Modifier is too long. Please keep it under 15 characters.",
            reply_to_message_id=message.message_id,
        )
        return

    # Try to find a profile matching the name
    profile = await asyncio.to_thread(rolling.find_profile_by_name, chat_id_str, name)

    if not profile:
        await message.reply_text(
            CREATE_FAILURE_NO_PROFILE.format(name=name),
            reply_to_message_id=message.message_id,
        )
        return

    # Check cost
    cost = rolling.RARITIES["Unique"]["recycle_cost"]
    unlocked_legendaries = await asyncio.to_thread(
        card_service.get_user_cards_by_rarity,
        user.user_id,
        user.username,
        "Legendary",
        chat_id_str,
        limit=None,
        unlocked=True,
    )

    if len(unlocked_legendaries) < cost:
        await message.reply_text(
            CREATE_INSUFFICIENT_CARDS_MESSAGE.format(required=cost),
            reply_to_message_id=message.message_id,
        )
        return

    # Check if modifier exists
    existing_modifiers = await asyncio.to_thread(
        card_service.get_modifier_counts_for_chat, chat_id_str
    )
    warning = ""
    if modifier in existing_modifiers:
        warning = CREATE_WARNING_EXISTING_MODIFIER.format(modifier=modifier)

    # Confirm
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm", callback_data=f"create_yes_{user.user_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"create_cancel_{user.user_id}"),
            ]
        ]
    )

    session_key = f"create_session_{chat_id_str}_{user.user_id}"
    context.user_data[session_key] = {
        "modifier": modifier,
        "profile": profile,
        "cost": cost,
        "timestamp": datetime.datetime.now().isoformat(),
    }

    await message.reply_text(
        CREATE_CONFIRM_MESSAGE.format(
            cost=cost,
            modifier=modifier,
            name=name,
        )
        + warning,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        reply_to_message_id=message.message_id,
    )


async def handle_create_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle create unique card confirmation callback."""
    query = update.callback_query
    await query.answer()

    data = query.data.split("_")
    action = data[1]  # yes or cancel
    user_id = int(data[2])

    if user_id != query.from_user.id:
        await query.answer(CREATE_NOT_YOURS_MESSAGE, show_alert=True)
        return

    chat_id_str = str(query.message.chat_id)
    session_key = f"create_session_{chat_id_str}_{user_id}"
    session = context.user_data.get(session_key)

    if not session:
        await query.edit_message_text("Session expired or invalid.")
        return

    if action == "cancel":
        del context.user_data[session_key]
        await query.edit_message_text(CREATE_CANCELLED_MESSAGE)
        return

    if action == "yes":
        # Double check cost
        cost = session["cost"]
        user = await asyncio.to_thread(user_service.get_user, user_id)
        unlocked_legendaries = await asyncio.to_thread(
            card_service.get_user_cards_by_rarity,
            user_id,
            user.username,
            "Legendary",
            chat_id_str,
            limit=None,
            unlocked=True,
        )

        if len(unlocked_legendaries) < cost:
            await query.edit_message_text(CREATE_INSUFFICIENT_CARDS_MESSAGE.format(required=cost))
            del context.user_data[session_key]
            return

        # Prepare cards to burn
        cards_to_burn = unlocked_legendaries[:cost]
        card_titles = [html.escape(card.title()) for card in cards_to_burn]

        # Remove keyboard
        await query.edit_message_reply_markup(reply_markup=None)

        # Start generation in background
        modifier = session["modifier"]
        profile = session["profile"]

        generation_task = asyncio.create_task(
            asyncio.to_thread(
                rolling.generate_unique_card,
                modifier,
                profile,
                gemini_util,
                UNIQUE_ADDENDUM,
            )
        )

        # Show burning animation
        message_id = query.message.message_id
        for idx in range(len(cards_to_burn)):
            text = build_burning_text(card_titles, idx + 1)
            try:
                await context.bot.edit_message_text(
                    chat_id=query.message.chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            await asyncio.sleep(1)

        try:
            await context.bot.edit_message_text(
                chat_id=query.message.chat_id,
                message_id=message_id,
                text=build_burning_text(card_titles, len(cards_to_burn), strike_all=True)
                + "\n\nCreating <b>Unique</b> card...",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        try:
            # Wait for generation
            generated_card = await generation_task

            # Add to DB
            card_id = await asyncio.to_thread(
                card_service.add_card_from_generated,
                generated_card,
                chat_id_str,
            )

            # Set owner
            await asyncio.to_thread(card_service.set_card_owner, card_id, user.username, user_id)

            # NOW delete the cards (skip in debug mode)
            if not DEBUG_MODE:
                card_ids = [c.id for c in cards_to_burn]
                await asyncio.to_thread(card_service.delete_cards, card_ids)

            # Send result
            card = await asyncio.to_thread(card_service.get_card, card_id)

            # Clean up session
            del context.user_data[session_key]

            # Send photo
            image_bytes = base64.b64decode(generated_card.image_b64)

            burned_block = "\n".join([f"<s>🔥{t}🔥</s>" for t in card_titles])

            caption = (
                CARD_CAPTION_BASE.format(
                    card_id=card.id,
                    card_title=html.escape(card.title()),
                    rarity=card.rarity,
                )
                + CARD_STATUS_CLAIMED.format(username=user.username)
                + f"\n\nBurned cards:\n\n<b>{burned_block}</b>"
            )

            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                message_thread_id=query.message.message_thread_id,
                photo=image_bytes,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )

            # Delete processing message
            await query.message.delete()

        except Exception as e:
            logger.error(f"Error creating unique card: {e}", exc_info=True)
            await query.edit_message_text(CREATE_FAILURE_UNEXPECTED)
            # Note: Cards are NOT deleted if we land here


# =============================================================================
# Recycle Card Handlers
# =============================================================================


@verify_user_in_chat
async def recycle(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Recycle cards of a given rarity for an upgraded card."""
    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type == ChatType.PRIVATE and not DEBUG_MODE:
        await message.reply_text(
            RECYCLE_DM_RESTRICTED_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    if not context.args:
        await message.reply_text(
            RECYCLE_USAGE_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    rarity_key = context.args[0].lower()
    if rarity_key not in RECYCLE_ALLOWED_RARITIES:
        await message.reply_text(
            RECYCLE_UNKNOWN_RARITY_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    rarity_name = RECYCLE_ALLOWED_RARITIES[rarity_key]
    upgrade_rarity = RECYCLE_UPGRADE_MAP[rarity_name]
    required_cards = get_recycle_required_cards(rarity_name)
    chat_id_str = str(chat.id)

    cards = await asyncio.to_thread(
        card_service.get_user_cards_by_rarity,
        user.user_id,
        user.username,
        rarity_name,
        chat_id_str,
        limit=None,
        unlocked=True,  # only consider non-locked cards
    )

    if len(cards) < required_cards:
        await message.reply_text(
            RECYCLE_INSUFFICIENT_CARDS_MESSAGE.format(
                required=required_cards,
                rarity=rarity_name.lower(),
            ),
            reply_to_message_id=message.message_id,
        )
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Yes!", callback_data=f"recycle_yes_{rarity_key}_{user.user_id}"
                ),
                InlineKeyboardButton(
                    "Cancel", callback_data=f"recycle_cancel_{rarity_key}_{user.user_id}"
                ),
            ]
        ]
    )

    await message.reply_text(
        RECYCLE_CONFIRM_MESSAGE.format(
            burn_count=required_cards,
            rarity=rarity_name,
            upgraded_rarity=upgrade_rarity,
        ),
        reply_markup=keyboard,
        reply_to_message_id=message.message_id,
        parse_mode=ParseMode.HTML,
    )


@verify_user_in_chat
async def handle_recycle_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle recycle confirmation callback."""
    query = update.callback_query
    if not query:
        return

    data_parts = query.data.split("_")
    if len(data_parts) < 4:
        await query.answer()
        return

    _, action, rarity_key, target_user_id_str = data_parts[:4]

    try:
        target_user_id = int(target_user_id_str)
    except ValueError:
        await query.answer("Unable to process this request.", show_alert=True)
        return

    if target_user_id != user.user_id:
        await query.answer(RECYCLE_NOT_YOURS_MESSAGE)
        return

    rarity_name = RECYCLE_ALLOWED_RARITIES.get(rarity_key)
    if not rarity_name:
        await query.answer(RECYCLE_UNKNOWN_RARITY_MESSAGE, show_alert=True)
        return

    if action == "cancel":
        await query.answer("Recycle cancelled.")
        try:
            await query.message.delete()
        except Exception:
            try:
                await query.edit_message_text("Recycle cancelled.")
            except Exception:
                pass
        return

    if action != "yes":
        await query.answer()
        return

    chat = update.effective_chat
    if not chat:
        await query.answer()
        return

    recycling_users = context.bot_data.setdefault("recycling_users", set())
    if user.user_id in recycling_users:
        await query.answer(RECYCLE_ALREADY_RUNNING_MESSAGE, show_alert=True)
        return

    recycling_users.add(user.user_id)

    chat_id = query.message.chat_id
    message_id = query.message.message_id
    upgrade_rarity = RECYCLE_UPGRADE_MAP.get(rarity_name)

    if not upgrade_rarity:
        await query.answer("Unable to upgrade this rarity.", show_alert=True)
        recycling_users.discard(user.user_id)
        return

    required_cards = get_recycle_required_cards(rarity_name)

    try:
        cards = await asyncio.to_thread(
            card_service.get_user_cards_by_rarity,
            user.user_id,
            user.username,
            rarity_name,
            str(chat_id),
            limit=None,
            unlocked=True,  # only consider non-locked cards
        )

        if len(cards) < required_cards:
            await query.answer(RECYCLE_FAILURE_NOT_ENOUGH_CARDS, show_alert=True)
            try:
                await query.edit_message_text(RECYCLE_FAILURE_NOT_ENOUGH_CARDS)
            except Exception:
                pass
            return

        cards_to_burn = random.sample(cards, required_cards)
        card_titles = [html.escape(card.title()) for card in cards_to_burn]

        await query.answer()
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        generation_task = asyncio.create_task(
            asyncio.to_thread(
                rolling.generate_card_for_chat,
                str(chat_id),
                gemini_util,
                upgrade_rarity,
                max_retries=MAX_BOT_IMAGE_RETRIES,
                source="roll",
            )
        )

        for idx in range(len(cards_to_burn)):
            text = build_burning_text(card_titles, idx + 1)
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            await asyncio.sleep(1)

        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=build_burning_text(card_titles, len(cards_to_burn), strike_all=True)
                + "\n\nGenerating upgraded card...",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        try:
            generated_card = await generation_task

            # Log the card generation details
            log_card_generation(generated_card, "recycle")
        except rolling.NoEligibleUserError:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=RECYCLE_FAILURE_NO_PROFILE,
            )
            return
        except rolling.ImageGenerationError:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=RECYCLE_FAILURE_IMAGE,
            )
            return
        except Exception as exc:
            logger.error("Error while generating recycled card: %s", exc)
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=RECYCLE_FAILURE_UNEXPECTED,
            )
            return

        new_card_id = await asyncio.to_thread(
            card_service.add_card_from_generated,
            generated_card,
            chat_id,
        )

        owner_username = user.username or f"user_{user.user_id}"
        claimed = await asyncio.to_thread(
            card_service.try_claim_card,
            new_card_id,
            owner_username,
            user.user_id,
        )
        if not claimed:
            logger.warning(
                "Failed to assign recycled card %s to user %s (%s)",
                new_card_id,
                owner_username,
                user.user_id,
            )

        card_ids_to_delete = [card.id for card in cards_to_burn]
        await asyncio.to_thread(card_service.delete_cards, card_ids_to_delete)

        burned_block = "\n".join([f"<s>🔥{card_title}🔥</s>" for card_title in card_titles])
        # Note: generated_card.card_title doesn't use Card.title() - it's directly from GeneratedCard
        final_caption = CARD_CAPTION_BASE.format(
            card_id=new_card_id,
            card_title=generated_card.card_title,
            rarity=generated_card.rarity,
        )
        final_caption += RECYCLE_RESULT_APPENDIX.format(
            burned_block=burned_block,
        )

        media = InputMediaPhoto(
            media=base64.b64decode(generated_card.image_b64),
            caption=final_caption,
            parse_mode=ParseMode.HTML,
        )

        message = await context.bot.edit_message_media(
            chat_id=chat_id,
            message_id=message_id,
            media=media,
        )

        # Save the file_id returned by Telegram for future use
        await save_card_file_id_from_message(message, new_card_id)

    finally:
        recycling_users.discard(user.user_id)
