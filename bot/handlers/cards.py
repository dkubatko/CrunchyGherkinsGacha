"""
Card-related command handlers.

This module contains handlers for refreshing card images and equipping
aspects onto cards.
"""

import asyncio
import base64
import html
import logging
from io import BytesIO
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from config import DEBUG_MODE, MAX_BOT_IMAGE_RETRIES, MINIAPP_URL_ENV, gemini_util
from handlers.helpers import (
    log_card_generation,
    save_card_file_id_from_message,
)
from settings.constants import (
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
    SLOTS_VIEW_IN_APP_LABEL,
    # Equip constants
    EQUIP_USAGE_MESSAGE,
    EQUIP_DM_RESTRICTED_MESSAGE,
    EQUIP_INVALID_IDS_MESSAGE,
    EQUIP_ASPECT_NOT_FOUND_MESSAGE,
    EQUIP_CARD_NOT_FOUND_MESSAGE,
    EQUIP_NOT_YOUR_ASPECT_MESSAGE,
    EQUIP_NOT_YOUR_CARD_MESSAGE,
    EQUIP_CHAT_MISMATCH_MESSAGE,
    EQUIP_CARD_LOCKED_MESSAGE,
    EQUIP_ASPECT_LOCKED_MESSAGE,
    EQUIP_ASPECT_EQUIPPED_MESSAGE,
    EQUIP_CAPACITY_MESSAGE,
    EQUIP_RARITY_MISMATCH_MESSAGE,
    EQUIP_NAME_TOO_LONG_MESSAGE,
    EQUIP_NAME_INVALID_CHARS_MESSAGE,
    EQUIP_CONFIRM_MESSAGE,
    EQUIP_CANCELLED_MESSAGE,
    EQUIP_ALREADY_RUNNING_MESSAGE,
    EQUIP_NOT_YOURS_MESSAGE,
    EQUIP_CRAFTING_MESSAGE,
    EQUIP_DB_FAILURE_MESSAGE,
    EQUIP_SUCCESS_MESSAGE,
    EQUIP_IMAGE_FAILURE_MESSAGE,
    RARITY_ORDER,
)
from utils import rolling
from utils.miniapp import encode_single_card_token
from repos import card_repo
from repos import claim_repo
from repos import aspect_repo
from repos import equip_session_repo
from managers import event_manager
from managers import aspect_manager
from utils.schemas import User, Card
from utils.decorators import verify_user_in_chat
from utils.events import (
    EventType,
    RefreshOutcome,
    EquipOutcome,
)

logger = logging.getLogger(__name__)


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

    card = await asyncio.to_thread(card_repo.get_card, card_id)
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
    balance = await asyncio.to_thread(claim_repo.get_claim_balance, user.user_id, chat_id_str)
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
    card = await asyncio.to_thread(card_repo.get_card, card_id)
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
    card = await asyncio.to_thread(card_repo.get_card, card_id)
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

    card = await asyncio.to_thread(card_repo.get_card, card_id)
    card_title = card.title(include_id=True, include_rarity=True) if card else f"Card {card_id}"
    chat_id_for_balance = session["chat_id"]

    # If user selected the original image (option 1), keep the original without updating
    if option_index == 1:
        latest_balance = await asyncio.to_thread(
            claim_repo.get_claim_balance, user.user_id, chat_id_for_balance
        )
        success_message = (
            f"<b>{card_title}</b>\n\nKept original image.\n\nBalance: {latest_balance}"
        )
    else:
        # Update the card with the new image
        chosen_image_b64 = options[selection_idx]
        await asyncio.to_thread(card_repo.update_card_image, card_id, chosen_image_b64)

        latest_balance = await asyncio.to_thread(
            claim_repo.get_claim_balance, user.user_id, chat_id_for_balance
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

    # Log refresh success event
    event_manager.log(
        EventType.REFRESH,
        RefreshOutcome.SUCCESS,
        user_id=user.user_id,
        chat_id=chat_id_for_balance,
        card_id=card_id,
        option_selected=option_index,
        kept_original=(option_index == 1),
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
    """Generate two refresh image options.

    For cards with equipped aspects, uses the equipped-card refresh path
    (``generate_refresh_equipped_image``) which generates from scratch
    using the character photo + all equipped aspect sphere images.
    """
    if card.aspect_count > 0:
        return await _generate_equipped_refresh_options(card, gemini_util, max_retries)

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


async def _generate_equipped_refresh_options(
    card: Card,
    gemini_util,
    max_retries: int,
) -> tuple[str, str]:
    """Generate two refresh options for a card with equipped aspects.

    Uses ``generate_refresh_equipped_image`` which starts from scratch
    with the character photo, rarity template, and all equipped aspect
    sphere images — producing a completely fresh interpretation.
    """
    # Get source profile image
    if not card.source_type or not card.source_id:
        raise rolling.InvalidSourceError(
            f"Card {card.id} has no source information "
            f"(source_type={card.source_type}, source_id={card.source_id})"
        )
    profile = await asyncio.to_thread(
        rolling.get_profile_for_source, card.source_type, card.source_id
    )

    # Gather all equipped aspect images
    equipped = await asyncio.to_thread(aspect_repo.get_aspects_for_card, card.id)
    aspects_data: list[tuple[str, bytes]] = []
    for ca in equipped:
        aspect_with_img = await asyncio.to_thread(
            aspect_repo.get_aspect_with_image, ca.aspect_id
        )
        if aspect_with_img and aspect_with_img.image_b64:
            aspects_data.append(
                (aspect_with_img.display_name, base64.b64decode(aspect_with_img.image_b64))
            )

    card_name = card.title()
    total_attempts = max(1, max_retries + 1)

    results: list[str] = []
    for attempt_idx in range(2):
        temperature = 1.0 + (0.25 * (attempt_idx + 1))
        last_error: Optional[Exception] = None

        for attempt in range(1, total_attempts + 1):
            try:
                image_b64 = await asyncio.to_thread(
                    gemini_util.generate_refresh_equipped_image,
                    card.rarity,
                    card_name,
                    aspects_data,
                    base_image_b64=profile.image_b64,
                    temperature=temperature,
                )
                if not image_b64:
                    raise rolling.ImageGenerationError("Empty image returned")
                results.append(image_b64)
                break
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Equipped refresh attempt %s/%s (option %s) failed for card %s: %s",
                    attempt,
                    total_attempts,
                    attempt_idx + 1,
                    card.id,
                    exc,
                )
                if attempt < total_attempts:
                    await asyncio.sleep(1)
        else:
            raise last_error or rolling.ImageGenerationError(
                "Equipped refresh failed after retries"
            )

    return results[0], results[1]


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
    points_deducted = False
    refresh_cost = 0
    active_chat_id = None
    try:
        card = await asyncio.to_thread(card_repo.get_card, card_id)
        if not card:
            await query.answer(REFRESH_CARD_NOT_FOUND_MESSAGE, show_alert=True)
            return

        if not await _validate_refresh_ownership(card, user):
            await query.answer(REFRESH_NOT_YOURS_MESSAGE, show_alert=True)
            return

        refresh_cost = get_refresh_cost(card.rarity)
        active_chat_id = card.chat_id or chat_id_str
        balance = await asyncio.to_thread(
            claim_repo.get_claim_balance, user.user_id, active_chat_id
        )

        if balance < refresh_cost:
            await query.answer(
                REFRESH_INSUFFICIENT_BALANCE_MESSAGE.format(balance=balance, cost=refresh_cost),
                show_alert=True,
            )
            return

        remaining_balance = await asyncio.to_thread(
            claim_repo.reduce_claim_points, user.user_id, active_chat_id, refresh_cost
        )
        points_deducted = remaining_balance is not None

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
                claim_repo.increment_claim_balance, user.user_id, active_chat_id, refresh_cost
            )
            # Log refresh error event
            event_manager.log(
                EventType.REFRESH,
                RefreshOutcome.ERROR,
                user_id=user.user_id,
                chat_id=active_chat_id,
                card_id=card_id,
                error_message=str(exc),
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
                claim_repo.increment_claim_balance, user.user_id, active_chat_id, refresh_cost
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
        if points_deducted:
            await asyncio.to_thread(
                claim_repo.increment_claim_balance, user.user_id, active_chat_id, refresh_cost
            )
            logger.info(
                "Refunded %d claim points to user %s after unexpected refresh error",
                refresh_cost,
                user.user_id,
            )
        await query.answer("Refresh failed due to an unexpected error.", show_alert=True)
        try:
            error_card = await asyncio.to_thread(card_repo.get_card, card_id)
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
# Equip Aspect Handlers
# =============================================================================

_EQUIP_INVALID_NAME_CHARS = set("<>&*_`")


def _validate_equip_name(name_prefix: str) -> Optional[str]:
    """Validate the equip name prefix.

    Returns an error message string if invalid, or ``None`` if valid.
    """
    if len(name_prefix) > 30:
        return EQUIP_NAME_TOO_LONG_MESSAGE
    if any(ch in _EQUIP_INVALID_NAME_CHARS for ch in name_prefix):
        return EQUIP_NAME_INVALID_CHARS_MESSAGE
    return None


def _rarity_index(rarity: str) -> int:
    """Return the index of a rarity in RARITY_ORDER (lower = more common)."""
    try:
        return RARITY_ORDER.index(rarity)
    except ValueError:
        return len(RARITY_ORDER)


@verify_user_in_chat
async def equip(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Equip an aspect onto a card."""
    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type == ChatType.PRIVATE and not DEBUG_MODE:
        await message.reply_text(
            EQUIP_DM_RESTRICTED_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    if not context.args or len(context.args) < 2:
        await message.reply_text(
            EQUIP_USAGE_MESSAGE,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=message.message_id,
        )
        return

    # Parse aspect_id and card_id
    try:
        aspect_id = int(context.args[0])
        card_id = int(context.args[1])
    except ValueError:
        await message.reply_text(
            EQUIP_INVALID_IDS_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    # Optional name prefix (remaining args joined)
    name_prefix_args = context.args[2:]
    name_prefix_raw = " ".join(name_prefix_args).strip() if name_prefix_args else None

    chat_id_str = str(chat.id)

    # Fetch aspect and card
    aspect = await asyncio.to_thread(aspect_repo.get_aspect_by_id, aspect_id)
    if not aspect:
        await message.reply_text(
            EQUIP_ASPECT_NOT_FOUND_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    card = await asyncio.to_thread(card_repo.get_card, card_id)
    if not card:
        await message.reply_text(
            EQUIP_CARD_NOT_FOUND_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    # Ownership checks
    if aspect.user_id != user.user_id:
        await message.reply_text(
            EQUIP_NOT_YOUR_ASPECT_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    if card.user_id != user.user_id:
        await message.reply_text(
            EQUIP_NOT_YOUR_CARD_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    # Chat membership
    if aspect.chat_id != chat_id_str:
        await message.reply_text(
            EQUIP_CHAT_MISMATCH_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    if not card.chat_id or card.chat_id != chat_id_str:
        await message.reply_text(
            EQUIP_CHAT_MISMATCH_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    # Lock checks
    if card.locked:
        await message.reply_text(
            EQUIP_CARD_LOCKED_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    if aspect.locked:
        await message.reply_text(
            EQUIP_ASPECT_LOCKED_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    # Check equipped status
    equipped_aspects = await asyncio.to_thread(aspect_repo.get_aspects_for_card, card_id)
    is_already_equipped = any(ca.aspect_id == aspect_id for ca in equipped_aspects)
    if is_already_equipped:
        await message.reply_text(
            EQUIP_ASPECT_EQUIPPED_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    # Capacity check
    if card.aspect_count >= 5:
        await message.reply_text(
            EQUIP_CAPACITY_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    # Rarity compatibility
    if aspect.rarity != "Unique":
        aspect_idx = _rarity_index(aspect.rarity)
        card_idx = _rarity_index(card.rarity)
        if aspect_idx > card_idx:
            await message.reply_text(
                EQUIP_RARITY_MISMATCH_MESSAGE.format(
                    aspect_rarity=aspect.rarity,
                    card_rarity=card.rarity,
                ),
                parse_mode=ParseMode.HTML,
                reply_to_message_id=message.message_id,
            )
            return

    # Resolve name prefix
    if name_prefix_raw:
        name_prefix = name_prefix_raw
    else:
        name_prefix = aspect.display_name or "Unknown"

    # Capitalize first letter
    name_prefix = name_prefix[0].upper() + name_prefix[1:] if name_prefix else name_prefix

    # Validate name
    name_error = _validate_equip_name(name_prefix)
    if name_error:
        await message.reply_text(
            name_error,
            reply_to_message_id=message.message_id,
        )
        return

    # Build new display title for the confirmation
    new_title = f"{name_prefix} {card.base_name}"
    card_title = card.title(include_id=True)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Equip!",
                    callback_data=f"equip_yes_{aspect_id}_{card_id}_{user.user_id}",
                ),
                InlineKeyboardButton(
                    "Cancel",
                    callback_data=f"equip_cancel_{aspect_id}_{card_id}_{user.user_id}",
                ),
            ]
        ]
    )

    # Store session data for the callback
    await asyncio.to_thread(
        equip_session_repo.create_or_replace,
        user_id=user.user_id,
        chat_id=chat_id_str,
        aspect_id=aspect_id,
        card_id=card_id,
        name_prefix=name_prefix,
        aspect_name=aspect.display_name or "Unknown",
        aspect_rarity=aspect.rarity,
        card_title=card.title(),
        new_title=new_title,
    )

    await message.reply_text(
        EQUIP_CONFIRM_MESSAGE.format(
            aspect_id=aspect_id,
            aspect_name=html.escape(aspect.display_name),
            aspect_rarity=aspect.rarity,
            card_id=card_id,
            card_title=card_title,
            card_rarity=card.rarity,
            new_title=html.escape(new_title),
            aspect_count=card.aspect_count,
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        reply_to_message_id=message.message_id,
    )


@verify_user_in_chat
async def handle_equip_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle equip confirmation callback."""
    query = update.callback_query
    if not query:
        return

    data_parts = query.data.split("_")
    # equip_<action>_<aspect_id>_<card_id>_<user_id>
    if len(data_parts) < 5:
        await query.answer("Invalid equip data.")
        return

    action = data_parts[1]
    try:
        aspect_id = int(data_parts[2])
        card_id = int(data_parts[3])
        target_user_id = int(data_parts[4])
    except ValueError:
        await query.answer("Invalid equip data.")
        return

    if target_user_id != user.user_id:
        await query.answer(EQUIP_NOT_YOURS_MESSAGE, show_alert=True)
        return

    chat = update.effective_chat
    chat_id_str = str(chat.id) if chat else None

    db_session = await asyncio.to_thread(
        equip_session_repo.get_session,
        user.user_id,
        chat_id_str,
        aspect_id,
        card_id,
    )

    if action == "cancel":
        await asyncio.to_thread(equip_session_repo.delete_session, user.user_id, chat_id_str)
        await query.answer(EQUIP_CANCELLED_MESSAGE)
        try:
            await query.message.delete()
        except Exception:
            try:
                await query.edit_message_text(EQUIP_CANCELLED_MESSAGE)
            except Exception:
                pass
        if chat_id_str:
            event_manager.log(
                EventType.EQUIP,
                EquipOutcome.FAILURE,
                user_id=user.user_id,
                chat_id=chat_id_str,
                card_id=card_id,
                aspect_id=aspect_id,
                reason="cancelled",
            )
        return

    if action != "yes":
        await query.answer()
        return

    if not db_session:
        await query.answer("Session expired or invalid.", show_alert=True)
        try:
            await query.edit_message_text("Session expired. Please try /equip again.")
        except Exception:
            pass
        return

    equipping_users = context.bot_data.setdefault("equipping_users", set())
    if user.user_id in equipping_users:
        await query.answer(EQUIP_ALREADY_RUNNING_MESSAGE, show_alert=True)
        return

    equipping_users.add(user.user_id)
    name_prefix = db_session.name_prefix
    aspect_name = db_session.aspect_name
    card_title = db_session.card_title
    new_title = db_session.new_title

    try:
        await query.answer()

        # Show crafting message
        try:
            await query.edit_message_text(
                EQUIP_CRAFTING_MESSAGE.format(
                    aspect_name=html.escape(aspect_name),
                    card_title=html.escape(card_title),
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        # Execute the atomic equip transaction
        equip_success = await asyncio.to_thread(
            aspect_manager.equip_aspect_on_card,
            aspect_id,
            card_id,
            user.user_id,
            name_prefix,
            chat_id_str,
        )

        if not equip_success:
            await query.edit_message_text(EQUIP_DB_FAILURE_MESSAGE)
            event_manager.log(
                EventType.EQUIP,
                EquipOutcome.FAILURE,
                user_id=user.user_id,
                chat_id=chat_id_str,
                card_id=card_id,
                aspect_id=aspect_id,
                reason="db_validation_failed",
            )
            return

        # --- Image generation phase ---
        # Retrieve the updated card with its image
        card_with_image = await asyncio.to_thread(card_repo.get_card_with_aspects, card_id)
        if not card_with_image:
            logger.error("Card %s not found after successful equip", card_id)
            await query.edit_message_text(
                EQUIP_IMAGE_FAILURE_MESSAGE.format(
                    card_id=card_id,
                    new_title=html.escape(new_title),
                    rarity=db_session.aspect_rarity,
                    aspect_count=card_with_image.aspect_count if card_with_image else "?",
                )
            )
            return

        # Gather equipped aspect images for Gemini
        equipped_aspects_data = await asyncio.to_thread(
            aspect_repo.get_aspects_for_card, card_id
        )

        existing_aspects: list[tuple[str, bytes]] = []
        new_aspect_image_bytes: Optional[bytes] = None

        for ca in equipped_aspects_data:
            aspect_with_img = await asyncio.to_thread(
                aspect_repo.get_aspect_with_image, ca.aspect_id
            )
            if not aspect_with_img or not aspect_with_img.image_b64:
                continue

            img_bytes = base64.b64decode(aspect_with_img.image_b64)
            if ca.aspect_id == aspect_id:
                # This is the newly equipped aspect
                new_aspect_image_bytes = img_bytes
            else:
                # Previously equipped aspect
                existing_aspects.append((aspect_with_img.display_name, img_bytes))

        new_aspect_count = card_with_image.aspect_count

        if new_aspect_image_bytes is None:
            logger.warning("Could not load image for newly equipped aspect %s", aspect_id)
            await query.edit_message_text(
                EQUIP_IMAGE_FAILURE_MESSAGE.format(
                    card_id=card_id,
                    new_title=html.escape(new_title),
                    rarity=card_with_image.rarity,
                    aspect_count=new_aspect_count,
                ),
                parse_mode=ParseMode.HTML,
            )
            return

        # Generate the transformed card image
        try:
            new_image_b64 = await asyncio.to_thread(
                gemini_util.generate_equipped_card_image,
                card_with_image.image_b64,
                existing_aspects,
                aspect_name,
                new_aspect_image_bytes,
                card_with_image.rarity,
                new_title,
            )
        except Exception as exc:
            logger.error("Equip image generation failed for card %s: %s", card_id, exc)
            new_image_b64 = None

        if new_image_b64:
            # Update the card image in DB
            await asyncio.to_thread(card_repo.update_card_image, card_id, new_image_b64)

            # Send the new card photo
            image_bytes = base64.b64decode(new_image_b64)

            caption = EQUIP_SUCCESS_MESSAGE.format(
                card_id=card_id,
                new_title=html.escape(new_title),
                rarity=card_with_image.rarity,
                aspect_count=new_aspect_count,
            )

            reply_markup = None
            if MINIAPP_URL_ENV:
                card_token = encode_single_card_token(card_id)
                card_url = f"{MINIAPP_URL_ENV}?startapp={card_token}"
                reply_markup = InlineKeyboardMarkup(
                    [[InlineKeyboardButton(SLOTS_VIEW_IN_APP_LABEL, url=card_url)]]
                )

            sent_message = await context.bot.send_photo(
                chat_id=query.message.chat_id,
                message_thread_id=query.message.message_thread_id,
                photo=image_bytes,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )

            await save_card_file_id_from_message(sent_message, card_id)

            # Delete the crafting message
            try:
                await query.message.delete()
            except Exception:
                pass
        else:
            # Image generation failed but equip succeeded
            await query.edit_message_text(
                EQUIP_IMAGE_FAILURE_MESSAGE.format(
                    card_id=card_id,
                    new_title=html.escape(new_title),
                    rarity=card_with_image.rarity,
                    aspect_count=new_aspect_count,
                ),
                parse_mode=ParseMode.HTML,
            )

    except Exception as exc:
        logger.exception("Unexpected error during equip for card %s: %s", card_id, exc)
        event_manager.log(
            EventType.EQUIP,
            EquipOutcome.FAILURE,
            user_id=user.user_id,
            chat_id=chat_id_str or "",
            card_id=card_id,
            aspect_id=aspect_id,
            error_message=str(exc),
        )
        try:
            await query.edit_message_text(
                "An unexpected error occurred during equip. Please try again later."
            )
        except Exception:
            pass
    finally:
        equipping_users.discard(user.user_id)
        try:
            await asyncio.to_thread(equip_session_repo.delete_session, user.user_id, chat_id_str)
        except Exception:
            pass
