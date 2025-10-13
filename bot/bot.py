import asyncio
import logging
import os
import sys
import base64
import datetime
import html
import json
import random
import threading
import urllib.parse
from typing import Optional
from io import BytesIO
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    ReactionTypeEmoji,
    WebAppInfo,
)
from telegram.constants import ParseMode, ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from dotenv import load_dotenv

from settings.constants import (
    REACTION_IN_PROGRESS,
    COLLECTION_CAPTION,
    CARD_CAPTION_BASE,
    CARD_STATUS_UNCLAIMED,
    CARD_STATUS_CLAIMED,
    CARD_STATUS_LOCKED,
    CARD_STATUS_ATTEMPTED,
    CARD_STATUS_REROLLING,
    CARD_STATUS_REROLLED,
    TRADE_REQUEST_MESSAGE,
    TRADE_COMPLETE_MESSAGE,
    TRADE_REJECTED_MESSAGE,
    TRADE_CANCELLED_MESSAGE,
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
    RARITIES,
    get_recycle_required_cards,
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
    LOCK_USAGE_MESSAGE,
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
    get_refresh_cost,
)
from settings.constants import get_lock_cost, get_spin_reward, get_claim_cost
from utils import gemini, database, rolling
from utils.decorators import verify_user, verify_user_in_chat, verify_admin
from utils.rolled_card import RolledCardManager, ClaimStatus
from utils.miniapp import (
    encode_miniapp_token,
    encode_casino_token,
)

# Load environment variables
load_dotenv()

gemini_util = gemini.GeminiUtil()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    force=True,
)
logger = logging.getLogger(__name__)

DEBUG_MODE = "--debug" in sys.argv

MAX_BOT_IMAGE_RETRIES = 2

# Use debug token when in debug mode, otherwise use production token
if DEBUG_MODE:
    TELEGRAM_TOKEN = os.getenv("DEBUG_TELEGRAM_AUTH_TOKEN")
else:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_AUTH_TOKEN")


def log_card_generation(generated_card, context="card generation"):
    """Log details about a generated card including its source."""
    logger.info(
        f"Generating card for {context}: {generated_card.source_type}:{generated_card.source_id} "
        f"-> ({generated_card.rarity}) {generated_card.modifier} {generated_card.base_name}"
    )


def get_time_until_next_roll(user_id, chat_id):
    """Calculate time until next roll (24 hours from last roll).
    Uses the same timezone as the database (system local time).
    """
    last_roll_time = database.get_last_roll_time(user_id, chat_id)
    if last_roll_time is None:
        return 0, 0  # Can roll immediately if never rolled before

    now = datetime.datetime.now()
    next_roll_time = last_roll_time + datetime.timedelta(hours=24)
    time_diff = next_roll_time - now

    if time_diff.total_seconds() <= 0:
        return 0, 0  # Can roll now

    hours = int(time_diff.total_seconds() // 3600)
    minutes = int((time_diff.total_seconds() % 3600) // 60)

    return hours, minutes


async def save_card_file_id_from_message(message, card_id: int) -> None:
    """
    Extract and save the Telegram file_id from a message containing a card photo.

    Args:
        message: The Telegram message object containing the photo
        card_id: The database ID of the card to update
    """
    if message and message.photo:
        file_id = message.photo[-1].file_id  # Get the largest photo size
        await asyncio.to_thread(database.update_card_file_id, card_id, file_id)
        logger.debug(f"Saved file_id for card {card_id}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register the user in the users table. DM-only."""
    message = update.message
    user = update.effective_user

    if not message or not user:
        return

    if update.effective_chat.type != ChatType.PRIVATE:
        await message.reply_text("Please DM me with /start to register.")
        return

    if not user.username:
        await message.reply_text(
            "You need a Telegram username to register. Please set one in Telegram settings and try again."
        )
        return

    user_exists = await asyncio.to_thread(database.user_exists, user.id)

    display_name = None
    if not user_exists:
        display_name = user.full_name or user.username

    await asyncio.to_thread(database.upsert_user, user.id, user.username, display_name, None)

    if user_exists:
        await message.reply_text("You're already registered! You're good to go.")
    else:
        await message.reply_text(
            "Welcome! You're registered and ready to play. Use /profile with a photo to personalize your card."
        )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display current profile info (no args) or update user's profile in DM, or add a character in group chats."""

    message = update.message
    user = update.effective_user

    if not message or not user:
        return

    # Check if it's a group chat or DM
    if update.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        # Group chat - add character functionality (admin only)
        admin_username = os.getenv("DEBUG_BOT_ADMIN" if DEBUG_MODE else "BOT_ADMIN")

        # Check if user is admin
        if not admin_username or user.username != admin_username:
            await message.reply_text(
                "Only the bot administrator can add characters in group chats."
            )
            return

        command_text = message.text or message.caption or ""
        parts = command_text.split(maxsplit=1)

        if len(parts) < 2 or not parts[1].strip():
            await message.reply_text(
                "Usage: /profile <character_name> (attach a photo with the command).\n\nTo view your profile, please DM me with /profile (no arguments)."
            )
            return

        character_name = parts[1].strip()

        if not message.photo:
            await message.reply_text(
                "Please attach a character image when using /profile in group chats."
            )
            return

        photo = message.photo[-1]
        telegram_file = await context.bot.get_file(photo.file_id)
        buffer = BytesIO()
        await telegram_file.download_to_memory(out=buffer)
        image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        # Set thinking reaction while processing
        if not DEBUG_MODE:
            await context.bot.set_message_reaction(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                reaction=[ReactionTypeEmoji(REACTION_IN_PROGRESS)],
            )

        try:
            chat_id = str(update.effective_chat.id)
            existing_character = await asyncio.to_thread(
                database.get_character_by_name, chat_id, character_name
            )

            if existing_character:
                updated = await asyncio.to_thread(
                    database.update_character_image, existing_character.id, image_b64
                )

                if updated:
                    await message.reply_text(
                        f"Character '{character_name}' updated! Existing ID {existing_character.id} now has the new image."
                    )
                else:
                    await message.reply_text(
                        "I couldn't update that character's image. Please try again or delete and re-add it."
                    )
            else:
                character_id = await asyncio.to_thread(
                    database.add_character, chat_id, character_name, image_b64
                )

                await message.reply_text(
                    f"Character '{character_name}' added with ID {character_id}! They will now be used for card generation."
                )
        finally:
            # Remove thinking reaction
            if not DEBUG_MODE:
                await context.bot.set_message_reaction(
                    chat_id=update.effective_chat.id,
                    message_id=update.message.message_id,
                    reaction=[],
                )
        return

    # DM functionality - existing user profile update
    if update.effective_chat.type != ChatType.PRIVATE:
        await message.reply_text("Please DM me to update your profile.")
        return

    if not user.username:
        await message.reply_text("Please set a Telegram username before updating your profile.")
        return

    exists = await asyncio.to_thread(database.user_exists, user.id)
    if not exists:
        await message.reply_text("Please send /start first so I can register you.")
        return

    command_text = message.text or message.caption or ""
    parts = command_text.split(maxsplit=1)

    # Handle /profile with no arguments - show current profile
    if len(parts) < 2 or not parts[1].strip():
        # Get user's current profile data
        user_data = await asyncio.to_thread(database.get_user, user.id)

        if not user_data or not user_data.display_name:
            await message.reply_text(
                "You don't have a profile set up yet.\nUsage: /profile <display_name> (attach a photo with the command)."
            )
            return

        # Build response message
        profile_text = f"👤 <b>Your Profile</b>\n\n"
        profile_text += f"Display Name: <b>{user_data.display_name}</b>\n"
        profile_text += f"Username: @{user_data.username}"

        # Prepare media to send
        media_group = []

        if user_data.profile_imageb64:
            profile_image_data = base64.b64decode(user_data.profile_imageb64)
            profile_media = InputMediaPhoto(media=profile_image_data, caption="🖼️ Profile Image")
            media_group.append(profile_media)

        if user_data.slot_iconb64:
            slot_icon_data = base64.b64decode(user_data.slot_iconb64)
            slot_media = InputMediaPhoto(media=slot_icon_data, caption="🎰 Slot Machine Icon")
            media_group.append(slot_media)

        # Send response
        if media_group:
            # Send profile text first
            await message.reply_text(profile_text, parse_mode=ParseMode.HTML)
            # Then send images
            await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media_group)
        else:
            profile_text += "\n\n📷 No profile image available"
            await message.reply_text(profile_text, parse_mode=ParseMode.HTML)

        return

    display_name = parts[1].strip()

    if not message.photo:
        await message.reply_text("Please attach a profile image when using /profile.")
        return

    photo = message.photo[-1]
    telegram_file = await context.bot.get_file(photo.file_id)
    buffer = BytesIO()
    await telegram_file.download_to_memory(out=buffer)
    image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    # Set thinking reaction while processing
    if not DEBUG_MODE:
        await context.bot.set_message_reaction(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
            reaction=[ReactionTypeEmoji(REACTION_IN_PROGRESS)],
        )

    try:
        await asyncio.to_thread(database.upsert_user, user.id, user.username, None, None)
        await asyncio.to_thread(database.update_user_profile, user.id, display_name, image_b64)

        await message.reply_text("Profile updated! Your new display name and image are saved.")
    finally:
        # Remove thinking reaction
        if not DEBUG_MODE:
            await context.bot.set_message_reaction(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                reaction=[],
            )


async def delete_character(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete characters by name (case-insensitive). Admin only."""

    message = update.message
    user = update.effective_user

    if not message or not user:
        return

    # Restrict to admin only
    admin_username = os.getenv("DEBUG_BOT_ADMIN" if DEBUG_MODE else "BOT_ADMIN")

    # Check if user is admin
    if not admin_username or user.username != admin_username:
        await message.reply_text("Only the bot administrator can delete characters.")
        return

    if not context.args or len(context.args) != 1:
        await message.reply_text("Usage: /delete <character_name>")
        return

    character_name = context.args[0].strip()

    if not character_name:
        await message.reply_text("Character name cannot be empty.")
        return

    deleted_count = await asyncio.to_thread(database.delete_characters_by_name, character_name)

    if deleted_count == 0:
        await message.reply_text(f"No characters found with the name '{character_name}'.")
    elif deleted_count == 1:
        await message.reply_text(f"Deleted 1 character named '{character_name}'.")
    else:
        await message.reply_text(f"Deleted {deleted_count} characters named '{character_name}'.")


@verify_user
async def enroll(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Add the calling user to the current chat."""

    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("/enroll can only be used in group chats.")
        return

    chat_id = str(chat.id)
    is_member = await asyncio.to_thread(database.is_user_in_chat, chat_id, user.user_id)

    if is_member:
        await message.reply_text("You're already enrolled in this chat.")
        return

    inserted = await asyncio.to_thread(database.add_user_to_chat, chat_id, user.user_id)

    if inserted:
        await message.reply_text("You're enrolled! Have fun out there.")
    else:
        await message.reply_text("You're now marked as part of this chat.")

    missing_parts = []
    if not user.display_name:
        missing_parts.append("display name")
    if not user.profile_imageb64:
        missing_parts.append("profile photo")

    if missing_parts:
        prompt = (
            "Heads up: I don't have your "
            + " and ".join(missing_parts)
            + ". DM me with /profile <display_name> and a photo to complete your profile."
        )
        await message.reply_text(prompt)


@verify_user
async def unenroll(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Remove the calling user from the current chat."""

    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("/unenroll can only be used in group chats.")
        return

    chat_id = str(chat.id)
    is_member = await asyncio.to_thread(database.is_user_in_chat, chat_id, user.user_id)

    if not is_member:
        await message.reply_text("You're not enrolled in this chat.")
        return

    removed = await asyncio.to_thread(database.remove_user_from_chat, chat_id, user.user_id)

    if removed:
        await message.reply_text(
            "You're unenrolled from this chat. Use /enroll to rejoin anytime.",
        )
    else:
        await message.reply_text("You're no longer marked as part of this chat.")


@verify_user_in_chat
async def casino(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
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
    miniapp_url = os.getenv("DEBUG_MINIAPP_URL" if DEBUG_MODE else "MINIAPP_URL")
    if not miniapp_url:
        await message.reply_text("Casino mini-app is not configured.")
        return

    app_url = f"{miniapp_url}?startapp={casino_token}"
    keyboard = [[InlineKeyboardButton("🎰 Open Casino!", url=app_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text("🎰 Ready to play at the casino?", reply_markup=reply_markup)


@verify_user_in_chat
async def roll(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Roll a new card."""
    chat_id_str = str(update.effective_chat.id)

    if update.effective_chat.type == ChatType.PRIVATE and not DEBUG_MODE:
        if not DEBUG_MODE:
            await context.bot.set_message_reaction(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                reaction=[ReactionTypeEmoji("🤡")],
            )
        await update.message.reply_text("Caught a cheater! Only allowed to roll in the group chat.")
        return

    rolling_users = context.bot_data.setdefault("rolling_users", set())

    if user.user_id in rolling_users:
        await update.message.reply_text(
            "Hang tight, I'm still finishing your previous roll.",
            reply_to_message_id=update.message.message_id,
        )
        return

    rolling_users.add(user.user_id)

    try:
        if not DEBUG_MODE:
            await context.bot.set_message_reaction(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                reaction=[ReactionTypeEmoji(REACTION_IN_PROGRESS)],
            )
        if not DEBUG_MODE:
            if not await asyncio.to_thread(database.can_roll, user.user_id, chat_id_str):
                hours, minutes = get_time_until_next_roll(user.user_id, chat_id_str)
                await update.message.reply_text(
                    f"You have already rolled for a card. Next roll in {hours} hours {minutes} minutes.",
                    reply_to_message_id=update.message.message_id,
                )
                if not DEBUG_MODE:
                    await context.bot.set_message_reaction(
                        chat_id=update.effective_chat.id,
                        message_id=update.message.message_id,
                        reaction=[],
                    )
                return

        generated_card = await asyncio.to_thread(
            rolling.generate_card_for_chat,
            chat_id_str,
            gemini_util,
            max_retries=MAX_BOT_IMAGE_RETRIES,
        )

        # Log the card generation details
        log_card_generation(generated_card, "roll")

        card_id = await asyncio.to_thread(
            database.add_card_from_generated,
            generated_card,
            update.effective_chat.id,
        )

        if not DEBUG_MODE:
            await asyncio.to_thread(database.record_roll, user.user_id, chat_id_str)

        # Award claim points based on the rolled card's rarity
        claim_reward = get_claim_cost(generated_card.rarity)
        await asyncio.to_thread(
            database.increment_claim_balance,
            user.user_id,
            chat_id_str,
            claim_reward,
        )

        # Create rolled card entry to track state
        roll_id = await asyncio.to_thread(database.create_rolled_card, card_id, user.user_id)

        # Use RolledCardManager to generate caption and keyboard
        rolled_card_manager = RolledCardManager(roll_id)
        caption = rolled_card_manager.generate_caption()
        reply_markup = rolled_card_manager.generate_keyboard()

        message = await update.message.reply_photo(
            photo=base64.b64decode(generated_card.image_b64),
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=update.message.message_id,
        )

        # Save the file_id returned by Telegram for future use
        await save_card_file_id_from_message(message, card_id)

    except rolling.NoEligibleUserError:
        await update.message.reply_text(
            "No enrolled players here have set both a display name and profile photo yet. DM me with /profile <display_name> and a picture to join the fun!",
            reply_to_message_id=update.message.message_id,
        )
        return
    except rolling.ImageGenerationError:
        await update.message.reply_text(
            "Sorry, I couldn't generate an image at the moment.",
            reply_to_message_id=update.message.message_id,
        )
        return
    except Exception as e:
        logger.error(f"Error in /roll: {e}")
        await update.message.reply_text(
            "An error occurred while rolling for a card.",
            reply_to_message_id=update.message.message_id,
        )
    finally:
        rolling_users.discard(user.user_id)
        if not DEBUG_MODE:
            await context.bot.set_message_reaction(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                reaction=[],
            )


def _build_burning_text(card_titles: list[str], revealed: int, strike_all: bool = False) -> str:
    if revealed <= 0:
        return "Burning cards..."

    lines = []
    for idx in range(revealed):
        line = f"🔥{card_titles[idx]}🔥"
        if strike_all or idx < revealed - 1:
            line = f"<s>{line}</s>"
        lines.append(line)

    return "Burning cards...\n\n" + "\n".join(lines)


@verify_user_in_chat
async def burn(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
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

    card = await asyncio.to_thread(database.get_card, card_id)
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
        username = await asyncio.to_thread(database.get_username_for_user_id, user.user_id)

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
    user: database.User,
) -> None:
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

        card = await asyncio.to_thread(database.get_card, card_id)
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
            username = await asyncio.to_thread(database.get_username_for_user_id, user.user_id)

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

        success = await asyncio.to_thread(database.delete_card, card_id)
        if not success:
            await query.answer(BURN_FAILURE_MESSAGE, show_alert=True)
            try:
                await query.edit_message_text(BURN_FAILURE_MESSAGE)
            except Exception:
                pass
            return

        new_spin_total = await asyncio.to_thread(
            database.increment_user_spins, user.user_id, chat_id_str, spin_reward
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


@verify_user_in_chat
async def refresh(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Refresh a card's image for 5 claim points."""
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

    card = await asyncio.to_thread(database.get_card, card_id)
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
    balance = await asyncio.to_thread(database.get_claim_balance, user.user_id, chat_id_str)
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


@verify_user_in_chat
async def handle_refresh_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Handle refresh confirmation/cancellation."""
    query = update.callback_query
    if not query:
        return

    data_parts = query.data.split("_")
    if len(data_parts) < 4:
        await query.answer("Invalid refresh data.")
        return

    _, action, card_id_str, target_user_id_str = data_parts[:4]

    try:
        card_id = int(card_id_str)
        target_user_id = int(target_user_id_str)
    except ValueError:
        await query.answer("Invalid refresh data.")
        return

    if target_user_id != user.user_id:
        await query.answer("This refresh prompt isn't for you!")
        return

    if action == "cancel":
        # Fetch card info for the message
        card = await asyncio.to_thread(database.get_card, card_id)
        if card:
            card_title = card.title(include_id=True, include_rarity=True)
            cancel_msg = REFRESH_CANCELLED_MESSAGE.format(
                card_title=card_title,
            )
        else:
            cancel_msg = "Refresh cancelled."
        try:
            await query.edit_message_caption(
                caption=cancel_msg, parse_mode=ParseMode.HTML, reply_markup=None
            )
        except Exception:
            pass
        await query.answer()
        return

    if action != "yes":
        await query.answer("Unknown action.")
        return

    refreshing_users = context.bot_data.setdefault("refreshing_users", set())
    if user.user_id in refreshing_users:
        await query.answer(REFRESH_ALREADY_RUNNING_MESSAGE)
        return

    refreshing_users.add(user.user_id)

    chat = update.effective_chat
    chat_id_str = str(chat.id) if chat else None

    try:
        # Fetch the card again
        card = await asyncio.to_thread(database.get_card, card_id)
        if not card:
            await query.answer(REFRESH_CARD_NOT_FOUND_MESSAGE, show_alert=True)
            return

        # Verify ownership again
        username = user.username
        if not username:
            return

        owns_card = card.user_id == user.user_id or (username and card.owner == username)
        if not owns_card:
            await query.answer(REFRESH_NOT_YOURS_MESSAGE, show_alert=True)
            return

        # Verify balance again
        refresh_cost = get_refresh_cost(card.rarity)
        balance = await asyncio.to_thread(database.get_claim_balance, user.user_id, chat_id_str)
        if balance < refresh_cost:
            await query.answer(
                REFRESH_INSUFFICIENT_BALANCE_MESSAGE.format(balance=balance, cost=refresh_cost),
                show_alert=True,
            )
            return

        # Show processing message
        await query.answer()
        card_title = card.title(include_id=True, include_rarity=True)
        processing_msg = REFRESH_PROCESSING_MESSAGE.format(
            card_title=card_title,
        )
        try:
            await query.edit_message_caption(
                caption=processing_msg, parse_mode=ParseMode.HTML, reply_markup=None
            )
        except Exception:
            pass

        # Regenerate the image
        try:
            new_image_b64 = await asyncio.to_thread(
                rolling.regenerate_card_image,
                card,
                gemini_util,
                max_retries=MAX_BOT_IMAGE_RETRIES,
            )
        except (
            rolling.ImageGenerationError,
            rolling.InvalidSourceError,
            rolling.NoEligibleUserError,
        ) as exc:
            logger.warning("Image regeneration failed for card %s: %s", card_id, exc)
            card_title = card.title(include_id=True, include_rarity=True)
            failure_msg = REFRESH_FAILURE_MESSAGE.format(
                card_title=card_title,
            )
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

        # Deduct claim points only after successful generation
        remaining_balance = await asyncio.to_thread(
            database.reduce_claim_points, user.user_id, chat_id_str, refresh_cost
        )

        if remaining_balance is None:
            # Balance check failed (shouldn't happen since we checked above)
            await query.answer(
                REFRESH_INSUFFICIENT_BALANCE_MESSAGE.format(balance=balance, cost=refresh_cost),
                show_alert=True,
            )
            try:
                await query.edit_message_caption(
                    caption=REFRESH_INSUFFICIENT_BALANCE_MESSAGE.format(
                        balance=balance, cost=refresh_cost
                    ),
                    parse_mode=ParseMode.HTML,
                    reply_markup=None,
                )
            except Exception:
                pass
            return

        # Update the card with the new image
        await asyncio.to_thread(database.update_card_image, card_id, new_image_b64)

        logger.info(
            "Card %s refreshed by user %s, remaining balance: %s",
            card_id,
            user.user_id,
            remaining_balance,
        )

        # Replace the old image with the new one
        card_title = card.title(include_id=True, include_rarity=True)
        success_message = REFRESH_SUCCESS_MESSAGE.format(
            card_title=card_title,
            remaining_balance=remaining_balance,
        )
        try:
            new_image_bytes = base64.b64decode(new_image_b64)
            edited_message = await query.edit_message_media(
                media=InputMediaPhoto(
                    media=new_image_bytes,
                    caption=success_message,
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=None,
            )
            # Save the new file_id from Telegram
            await save_card_file_id_from_message(edited_message, card_id)
        except Exception as e:
            logger.warning("Failed to update message with new image: %s", e)
            # Fallback to just updating caption if media edit fails
            try:
                await query.edit_message_caption(
                    caption=success_message, parse_mode=ParseMode.HTML, reply_markup=None
                )
            except Exception:
                pass

    except Exception as exc:
        logger.exception("Unexpected error during refresh for card %s: %s", card_id, exc)
        await query.answer("Refresh failed due to an unexpected error.", show_alert=True)
        try:
            # Try to get card info for a better error message
            error_card = await asyncio.to_thread(database.get_card, card_id)
            if error_card:
                error_title = error_card.title(include_id=True, include_rarity=True)
                error_msg = REFRESH_FAILURE_MESSAGE.format(
                    card_title=error_title,
                )
            else:
                error_msg = "Refresh failed. Image generation is unavailable right now. Your claim points were not deducted."
            await query.edit_message_caption(
                caption=error_msg, parse_mode=ParseMode.HTML, reply_markup=None
            )
        except Exception:
            pass
    finally:
        refreshing_users.discard(user.user_id)


@verify_user_in_chat
async def recycle(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
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
        database.get_user_cards_by_rarity,
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
    user: database.User,
) -> None:
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
            database.get_user_cards_by_rarity,
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
            )
        )

        for idx in range(len(cards_to_burn)):
            text = _build_burning_text(card_titles, idx + 1)
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
                text=_build_burning_text(card_titles, len(cards_to_burn), strike_all=True)
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
            database.add_card_from_generated,
            generated_card,
            chat_id,
        )

        owner_username = user.username or f"user_{user.user_id}"
        await asyncio.to_thread(
            database.claim_card,
            new_card_id,
            owner_username,
            user.user_id,
        )

        for card in cards_to_burn:
            await asyncio.to_thread(database.nullify_card_owner, card.id)

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

        await query.answer("Recycled! Enjoy your new card!", show_alert=False)

    finally:
        recycling_users.discard(user.user_id)


@verify_user_in_chat
async def handle_reroll(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Handle reroll button click."""
    query = update.callback_query

    data_parts = query.data.split("_")
    roll_id = int(data_parts[1])

    rolled_card_manager = RolledCardManager(roll_id)

    if not rolled_card_manager.is_valid():
        await query.answer("Card not found!", show_alert=True)
        return

    active_card = rolled_card_manager.card
    if active_card is None:
        await query.answer("Card data unavailable", show_alert=True)
        return

    # Check if the user clicking can reroll this card
    if not rolled_card_manager.can_user_reroll(user.user_id):
        rolled_card = rolled_card_manager.rolled_card
        if rolled_card and rolled_card.original_roller_id != user.user_id:
            await query.answer("Only the original roller can reroll this card!", show_alert=True)
        elif rolled_card_manager.is_reroll_expired():
            await query.answer("Reroll has expired", show_alert=True)

            caption = rolled_card_manager.generate_caption()
            reply_markup = rolled_card_manager.generate_keyboard()
            await query.edit_message_caption(
                caption=caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML
            )
        else:
            await query.answer("Cannot reroll this card", show_alert=True)
        return

    original_card = rolled_card_manager.original_card or active_card
    original_owner_id = active_card.user_id
    original_claim_chat_id = active_card.chat_id
    if original_claim_chat_id is None and query.message:
        original_claim_chat_id = str(query.message.chat_id)
    elif original_claim_chat_id is not None:
        original_claim_chat_id = str(original_claim_chat_id)

    try:
        # Set being_rerolled status and update UI
        rolled_card_manager.set_being_rerolled(True)
        rerolling_caption = rolled_card_manager.generate_caption()
        await query.edit_message_caption(caption=rerolling_caption, parse_mode=ParseMode.HTML)

        # Answer callback query immediately to avoid timeout
        await query.answer("Rerolling card...")

        downgraded_rarity = rolling.get_downgraded_rarity(original_card.rarity)
        chat_id_for_roll = active_card.chat_id or (
            str(query.message.chat_id) if query.message else None
        )
        if chat_id_for_roll is None:
            raise ValueError("Unable to resolve chat id for reroll")

        generated_card = await asyncio.to_thread(
            rolling.generate_card_for_chat,
            str(chat_id_for_roll),
            gemini_util,
            downgraded_rarity,
            max_retries=MAX_BOT_IMAGE_RETRIES,
        )

        # Log the card generation details
        log_card_generation(generated_card, "reroll")

        # Add new card to database
        new_card_chat_id = active_card.chat_id or (query.message.chat_id if query.message else None)
        new_card_id = await asyncio.to_thread(
            database.add_card_from_generated,
            generated_card,
            new_card_chat_id,
        )

        # Nullify the original card's owner (preserves history)
        await asyncio.to_thread(database.nullify_card_owner, active_card.id)

        # Update rolled card state to point to the new card
        rolled_card_manager.mark_rerolled(new_card_id)

        # Generate caption and keyboard for the new card
        caption = rolled_card_manager.generate_caption()
        reply_markup = rolled_card_manager.generate_keyboard()

        # Update message with new image and caption
        message = await query.edit_message_media(
            media=InputMediaPhoto(
                media=base64.b64decode(generated_card.image_b64),
                caption=caption,
                parse_mode=ParseMode.HTML,
            ),
            reply_markup=reply_markup,
        )

        # Save the file_id returned by Telegram for future use
        await save_card_file_id_from_message(message, new_card_id)

        # If original card was claimed, give the claimer a claim point back
        if original_owner_id is not None and original_claim_chat_id is not None:
            await asyncio.to_thread(
                database.increment_claim_balance,
                original_owner_id,
                original_claim_chat_id,
            )
    except rolling.NoEligibleUserError:
        # Restore original state on error
        rolled_card_manager.set_being_rerolled(False)
        original_caption = rolled_card_manager.generate_caption()
        original_markup = rolled_card_manager.generate_keyboard()
        await query.edit_message_caption(
            caption=original_caption,
            reply_markup=original_markup,
            parse_mode=ParseMode.HTML,
        )
        await query.answer(
            "No enrolled players here have set both a display name and profile photo yet.",
            show_alert=True,
        )
    except rolling.ImageGenerationError:
        # Restore original state on error
        rolled_card_manager.set_being_rerolled(False)
        original_caption = rolled_card_manager.generate_caption()
        original_markup = rolled_card_manager.generate_keyboard()
        await query.edit_message_caption(
            caption=original_caption,
            reply_markup=original_markup,
            parse_mode=ParseMode.HTML,
        )
        await query.answer("Sorry, couldn't generate a new image!", show_alert=True)
    except Exception as e:
        logger.error(f"Error in reroll: {e}")
        # Restore original state on error
        try:
            rolled_card_manager.set_being_rerolled(False)
            original_caption = rolled_card_manager.generate_caption()
            original_markup = rolled_card_manager.generate_keyboard()
            await query.edit_message_caption(
                caption=original_caption,
                reply_markup=original_markup,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        # Try to answer callback query, but don't fail if it times out
        try:
            await query.answer("An error occurred during reroll!", show_alert=True)
        except Exception as callback_error:
            logger.warning(f"Failed to answer callback query: {callback_error}")


@verify_user_in_chat
async def handle_lock(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
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
async def claim_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
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
    else:
        # Card already claimed - check if it's owned by the same user
        owner = card.owner
        if owner == user.username:
            # Show success message with current balance for user's own card
            remaining_balance = claim_result.balance
            if remaining_balance is None and chat_id and user.user_id:
                remaining_balance = await asyncio.to_thread(
                    database.get_claim_balance, user.user_id, chat_id
                )
            await query.answer(_build_claim_message(remaining_balance), show_alert=True)
        else:
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
async def balance(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
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
        target_user_id = await asyncio.to_thread(database.get_user_id_by_username, target_username)
        if target_user_id is None:
            if message:
                await message.reply_text(
                    f"@{target_username} doesn't exist or isn't enrolled yet.",
                    reply_to_message_id=getattr(message, "message_id", None),
                )
            return

        is_member = await asyncio.to_thread(database.is_user_in_chat, chat_id, target_user_id)
        if not is_member:
            if message:
                await message.reply_text(
                    f"@{target_username} isn't enrolled in this chat.",
                    reply_to_message_id=getattr(message, "message_id", None),
                )
            return

        resolved_username = await asyncio.to_thread(
            database.get_username_for_user_id, target_user_id
        )
        display_username = resolved_username or target_username
    else:
        target_user_id = user.user_id
        display_username = user.username

    balance_value = await asyncio.to_thread(database.get_claim_balance, target_user_id, chat_id)
    point_label = "point" if balance_value == 1 else "points"

    spin_count = await asyncio.to_thread(
        database.get_or_update_user_spins_with_daily_refresh,
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
    user: database.User,
) -> None:
    """Display user's card collection."""

    chat = update.effective_chat
    chat_id_filter = None
    if chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        chat_id_filter = str(chat.id)
    if chat and chat.type != ChatType.PRIVATE:
        is_member = await asyncio.to_thread(database.is_user_in_chat, str(chat.id), user.user_id)
        if not is_member:
            prompt = "You're not enrolled in this chat yet. Use /enroll in this chat to join."
            if update.callback_query:
                await update.callback_query.answer(prompt, show_alert=True)
            effective_message = update.effective_message
            if effective_message:
                await effective_message.reply_text(prompt)
            return

    viewed_username_key: Optional[str] = None

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
        target_user_id = await asyncio.to_thread(database.get_user_id_by_username, target_username)
        if target_user_id is None:
            await update.message.reply_text(
                f"@{target_username} doesn't exist or isn't enrolled yet.",
                reply_to_message_id=update.message.message_id,
            )
            return

        # Check if the target user exists by trying to get their collection
        target_cards = await asyncio.to_thread(
            database.get_user_collection, target_user_id, chat_id_filter
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
            database.get_username_for_user_id, target_user_id
        )
        display_username = resolved_username or target_username
        viewed_user_id = target_user_id
        viewed_username_key = resolved_username or target_username
    else:
        # Default to current user's collection
        cards = await asyncio.to_thread(database.get_user_collection, user.user_id, chat_id_filter)
        resolved_username = await asyncio.to_thread(database.get_username_for_user_id, user.user_id)
        display_username = resolved_username or user.username
        viewed_user_id = user.user_id
        viewed_username_key = resolved_username or user.username

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

    viewed_username_key = viewed_username_key or f"user_{viewed_user_id}"

    collection_indices = context.user_data.setdefault("collection_index", {})
    collection_indices[viewed_username_key] = 0

    total_cards = len(cards)
    current_index = 0

    card_with_image = await asyncio.to_thread(database.get_card, cards[current_index].id)
    if not card_with_image:
        await update.message.reply_text("Card not found.")
        return

    card = cards[current_index]
    lock_icon = "🔒" if card.locked else ""
    card_title = card.title()
    rarity = card.rarity

    caption = COLLECTION_CAPTION.format(
        lock_icon=lock_icon,
        card_id=card.id,
        card_title=card_title,
        rarity=rarity,
        current_index=current_index + 1,
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

    # Add miniapp button
    miniapp_url = os.getenv("DEBUG_MINIAPP_URL" if DEBUG_MODE else "MINIAPP_URL")
    if miniapp_url:
        # New explicit token format (u-/uc-) consumed by miniapp (see telegram.ts)
        token = encode_miniapp_token(viewed_user_id, chat_id_filter)
        app_url = f"{miniapp_url}?startapp={token}"
        keyboard.append([InlineKeyboardButton("View in the app!", url=app_url)])

    keyboard.append(
        [
            InlineKeyboardButton(
                "Close", callback_data=f"collection_close_{user.user_id}_{viewed_user_id}"
            )
        ]
    )
    reply_markup = InlineKeyboardMarkup(keyboard)

    media = card_with_image.get_media()

    # For new collection requests (command invocations only)
    try:
        message = await update.message.reply_photo(
            photo=media,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=update.message.message_id,
        )
        # Always update file_id with what Telegram returns
        if message and message.photo:
            new_file_id = message.photo[-1].file_id
            await asyncio.to_thread(database.update_card_file_id, card.id, new_file_id)
    except Exception as e:
        logger.warning(
            f"Failed to send photo using file_id for card {card.id}, falling back to base64: {e}"
        )
        # Fallback to base64 upload
        try:
            message = await update.message.reply_photo(
                photo=base64.b64decode(card_with_image.image_b64),
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=update.message.message_id,
            )
            # Update file_id with the new one from Telegram
            if message and message.photo:
                new_file_id = message.photo[-1].file_id
                await asyncio.to_thread(database.update_card_file_id, card.id, new_file_id)
        except Exception as fallback_error:
            logger.error(
                f"Failed to send photo even with base64 fallback for card {card.id}: {fallback_error}"
            )
            await update.message.reply_text(
                f"Error displaying card {card.id}. Please try again.",
                reply_to_message_id=update.message.message_id,
            )


@verify_user
async def handle_collection_navigation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
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
        is_member = await asyncio.to_thread(database.is_user_in_chat, str(chat.id), user.user_id)
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
    cards = await asyncio.to_thread(database.get_user_collection, viewed_user_id, chat_id_filter)
    if not cards:
        await query.answer("No cards found.", show_alert=True)
        return

    # Update display_username for the viewed user
    resolved_username = await asyncio.to_thread(database.get_username_for_user_id, viewed_user_id)
    display_username = resolved_username or f"user_{viewed_user_id}"
    viewed_username_key = resolved_username or f"user_{viewed_user_id}"

    total_cards = len(cards)
    collection_indices = context.user_data.setdefault("collection_index", {})
    current_index = collection_indices.get(viewed_username_key, 0)

    if current_index >= total_cards or current_index < 0:
        current_index %= total_cards

    if "prev" in query.data:
        current_index = (current_index - 1) % total_cards
    elif "next" in query.data:
        current_index = (current_index + 1) % total_cards
    else:
        await query.answer()
        return

    collection_indices[viewed_username_key] = current_index

    # Get card details
    card_with_image = await asyncio.to_thread(database.get_card, cards[current_index].id)
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

    # Add miniapp button
    miniapp_url = os.getenv("DEBUG_MINIAPP_URL" if DEBUG_MODE else "MINIAPP_URL")
    if miniapp_url:
        # New explicit token format (u-/uc-) consumed by miniapp (see telegram.ts)
        token = encode_miniapp_token(viewed_user_id, chat_id_filter)

        if DEBUG_MODE:
            app_url = f"{miniapp_url}?v={token}"
        else:
            app_url = f"{miniapp_url}?startapp={token}"
        keyboard.append([InlineKeyboardButton("View in the app!", url=app_url)])

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
        # Always update file_id with what Telegram returns
        if message and message.photo:
            new_file_id = message.photo[-1].file_id
            await asyncio.to_thread(database.update_card_file_id, card.id, new_file_id)
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
            # Update file_id with the new one from Telegram
            if message and message.photo:
                new_file_id = message.photo[-1].file_id
                await asyncio.to_thread(database.update_card_file_id, card.id, new_file_id)
        except Exception as fallback_error:
            logger.error(
                f"Failed to edit message media even with base64 fallback for card {card.id}: {fallback_error}"
            )
            await query.answer(
                f"Error displaying card {card.id}. Please try again.", show_alert=True
            )
            return

    await query.answer()


async def _get_user_targets_for_stats(
    chat_id: str, is_private_chat: bool, user: database.User, args: list[str]
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
        target_user_id = await asyncio.to_thread(database.get_user_id_by_username, target_username)

        if target_user_id is None:
            raise ValueError(f"@{target_username} doesn't exist or isn't enrolled yet.")

        is_member = await asyncio.to_thread(database.is_user_in_chat, chat_id, target_user_id)
        if not is_member:
            raise ValueError(f"@{target_username} isn't enrolled in this chat.")

        targets.append((target_username, target_user_id))
    else:
        # All users in chat
        chat_scope = None if is_private_chat else chat_id
        usernames = await asyncio.to_thread(database.get_all_users_with_cards, chat_scope)

        if not usernames:
            raise ValueError("No users have claimed any cards yet.")

        for username in usernames:
            user_id = await asyncio.to_thread(database.get_user_id_by_username, username)
            targets.append((username, user_id))

    return targets


async def _format_user_stats(username: str, user_id: Optional[int], chat_id: str) -> str:
    """Format stats for a single user."""
    user_stats = await asyncio.to_thread(database.get_user_stats, username)

    if user_id is not None:
        balance_value = await asyncio.to_thread(database.get_claim_balance, user_id, chat_id)
        point_label = "point" if balance_value == 1 else "points"
        balance_line = f"{balance_value} {point_label}"

        spin_count = await asyncio.to_thread(
            database.get_or_update_user_spins_with_daily_refresh,
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
    user: database.User,
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


@verify_user_in_chat
async def trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
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

    card1 = await asyncio.to_thread(database.get_card, card_id1)
    card2 = await asyncio.to_thread(database.get_card, card_id2)

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
    miniapp_url = os.getenv("DEBUG_MINIAPP_URL" if DEBUG_MODE else "MINIAPP_URL")
    card1_url = None
    card2_url = None
    if miniapp_url:
        from utils.miniapp import encode_single_card_token

        card1_token = encode_single_card_token(card_id1)
        card2_token = encode_single_card_token(card_id2)
        card1_url = f"{miniapp_url}?startapp={card1_token}"
        card2_url = f"{miniapp_url}?startapp={card2_token}"

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
async def lock_card_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Initiate lock/unlock for a card by ID."""
    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type == ChatType.PRIVATE and not DEBUG_MODE:
        await message.reply_text("Only allowed to lock cards in the group chat.")
        return

    if len(context.args) != 1:
        await message.reply_text(LOCK_USAGE_MESSAGE)
        return

    try:
        card_id = int(context.args[0])
    except ValueError:
        await message.reply_text("Card ID must be a number.")
        return

    card = await asyncio.to_thread(database.get_card, card_id)

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
    user: database.User,
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
    card = await asyncio.to_thread(database.get_card, card_id)
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
        await asyncio.to_thread(database.set_card_locked, card_id, False)
        response_text = f"🔓 <b>{card_title}</b> unlocked!"
        await query.answer(f"{card_title} unlocked!", show_alert=False)
    else:
        # Lock the card (consumes configured claim points)
        # First check if user has enough balance
        current_balance = await asyncio.to_thread(database.get_claim_balance, user.user_id, chat_id)

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
            database.reduce_claim_points, user.user_id, chat_id, lock_cost
        )

        if remaining_balance is None:
            # This shouldn't happen since we checked above, but handle it anyway
            current_balance = await asyncio.to_thread(
                database.get_claim_balance, user.user_id, chat_id
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
        await asyncio.to_thread(database.set_card_locked, card_id, True)
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
async def reject_trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Handle trade rejection or cancellation (if initiator)."""
    query = update.callback_query

    _, _, card_id1_str, card_id2_str = query.data.split("_")
    card_id1 = int(card_id1_str)
    card_id2 = int(card_id2_str)

    card1 = await asyncio.to_thread(database.get_card, card_id1)
    card2 = await asyncio.to_thread(database.get_card, card_id2)

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

    # Use TRADE_CANCELLED_MESSAGE if initiator pressed Reject, otherwise TRADE_REJECTED_MESSAGE
    if is_initiator:
        message_text = TRADE_CANCELLED_MESSAGE.format(
            user1_username=user1_username,
            card1_title=card1.title(include_rarity=True),
            user2_username=user2_username,
            card2_title=card2.title(include_rarity=True),
        )
    else:
        message_text = TRADE_REJECTED_MESSAGE.format(
            user1_username=user1_username,
            card1_title=card1.title(include_rarity=True),
            user2_username=user2_username,
            card2_title=card2.title(include_rarity=True),
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
    user: database.User,
) -> None:
    """Handle trade acceptance."""
    query = update.callback_query

    _, _, card_id1_str, card_id2_str = query.data.split("_")
    card_id1 = int(card_id1_str)
    card_id2 = int(card_id2_str)

    card1 = await asyncio.to_thread(database.get_card, card_id1)
    card2 = await asyncio.to_thread(database.get_card, card_id2)

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

    success = await asyncio.to_thread(database.swap_card_owners, card_id1, card_id2)

    if success:
        message_text = TRADE_COMPLETE_MESSAGE.format(
            user1_username=user1_username,
            card1_title=card1.title(include_rarity=True),
            user2_username=user2_username,
            card2_title=card2.title(include_rarity=True),
        )
    else:
        message_text = "Trade failed. Please try again."

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


@verify_admin
async def spins(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Add spins to all members of the current chat. Admin only."""
    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    # Ensure it's used in a group chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text(
            "/spins can only be used in group chats.",
            reply_to_message_id=message.message_id,
        )
        return

    # Validate arguments
    if not context.args or len(context.args) != 1:
        await message.reply_text(
            "Usage: /spins <number>\nExample: /spins 5",
            reply_to_message_id=message.message_id,
        )
        return

    try:
        spins_to_add = int(context.args[0])
    except ValueError:
        await message.reply_text(
            "The number of spins must be a valid integer.",
            reply_to_message_id=message.message_id,
        )
        return

    if spins_to_add <= 0:
        await message.reply_text(
            "The number of spins must be a positive number.",
            reply_to_message_id=message.message_id,
        )
        return

    if spins_to_add > 100:
        await message.reply_text(
            "Cannot add more than 100 spins at once.",
            reply_to_message_id=message.message_id,
        )
        return

    try:
        chat_id = str(chat.id)
        # Get all users enrolled in this chat
        all_user_ids = await asyncio.to_thread(database.get_all_chat_users, chat_id)

        if not all_user_ids:
            await message.reply_text(
                "No users are enrolled in this chat yet.",
                reply_to_message_id=message.message_id,
            )
            return

        # Add spins to all users
        successful_count = 0
        for user_id in all_user_ids:
            try:
                await asyncio.to_thread(
                    database.increment_user_spins, user_id, chat_id, spins_to_add
                )
                successful_count += 1
            except Exception as e:
                logger.warning(f"Failed to add spins to user {user_id}: {e}")

        # Report results
        plural = "spin" if spins_to_add == 1 else "spins"
        user_plural = "user" if successful_count == 1 else "users"

        await message.reply_text(
            f"✅ Successfully added {spins_to_add} {plural} to {successful_count} {user_plural} in this chat!\n\nUse /slots -- happy gambling! 🎰",
            reply_to_message_id=message.message_id,
        )

        logger.info(
            f"@{user.username} executed /spins {spins_to_add} command, affected {successful_count} users"
        )

    except Exception as e:
        logger.error(f"Error in /spins command: {e}")
        await message.reply_text(
            "❌ An error occurred while adding spins. Please try again.",
            reply_to_message_id=message.message_id,
        )


@verify_user_in_chat
async def reload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Reload command - clears all file_ids. Only accessible to admin."""
    # Get admin username from environment variable
    admin_username = os.getenv("BOT_ADMIN")

    # Silently ignore if user is not the admin
    if not admin_username or user.username != admin_username:
        return

    try:
        # Clear all file_ids from database
        affected_rows = await asyncio.to_thread(database.clear_all_file_ids)

        await update.message.reply_text(
            f"🔄 Reload complete! Cleared file_ids for {affected_rows} cards.\n"
            f"All cards will be re-uploaded on next display.",
            reply_to_message_id=update.message.message_id,
        )

        logger.info(f"@{user.username} executed /reload command, cleared {affected_rows} file_ids")

    except Exception as e:
        logger.error(f"Error in /reload: {e}")
        await update.message.reply_text(
            "❌ An error occurred while executing the reload command.",
            reply_to_message_id=update.message.message_id,
        )


@verify_admin
async def set_thread(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Set the thread ID for the current chat. Admin only.

    Usage: /set_thread [main|trade|clear]
    If no argument is provided, defaults to 'main'.
    Use 'clear' to remove all thread configurations.
    """
    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    # Ensure it's used in a group chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text(
            "/set_thread can only be used in group chats.",
            reply_to_message_id=message.message_id,
        )
        return

    # Parse thread type argument (default to 'main')
    thread_type = "main"
    is_clear = False
    if context.args:
        arg = context.args[0].lower()
        if arg == "clear":
            is_clear = True
        elif arg in ("main", "trade"):
            thread_type = arg
        else:
            await message.reply_text(
                "❌ Invalid thread type. Use 'main', 'trade', or 'clear'.\n\nUsage: /set_thread [main|trade|clear]",
                reply_to_message_id=message.message_id,
            )
            return

    try:
        chat_id = str(chat.id)

        # Handle clear command
        if is_clear:
            success = await asyncio.to_thread(database.clear_thread_ids, chat_id)
            if success:
                await message.reply_text(
                    "✅ All thread configurations have been cleared for this chat.\n\n"
                    "Bot notifications will now be posted to the main chat.",
                    reply_to_message_id=message.message_id,
                )
                logger.info(f"@{user.username} cleared all thread_ids for chat_id={chat_id}")
            else:
                await message.reply_text(
                    "ℹ️ No thread configurations found to clear.",
                    reply_to_message_id=message.message_id,
                )
            return

        # Get the thread_id from the message
        thread_id = message.message_thread_id

        if thread_id is None:
            await message.reply_text(
                "❌ No thread detected. This command must be used within a forum topic/thread.",
                reply_to_message_id=message.message_id,
            )
            return

        success = await asyncio.to_thread(database.set_thread_id, chat_id, thread_id, thread_type)

        if success:
            type_label = "main" if thread_type == "main" else "trade"
            await message.reply_text(
                f"✅ Thread ID {thread_id} has been set as the '{type_label}' thread for this chat.\n\n"
                f"Bot notifications for {type_label} activities will now be posted to this thread.",
                reply_to_message_id=message.message_id,
            )
            logger.info(
                f"@{user.username} set thread_id={thread_id} (type={thread_type}) for chat_id={chat_id}"
            )
        else:
            await message.reply_text(
                "❌ Failed to set thread ID. Please try again.",
                reply_to_message_id=message.message_id,
            )

    except Exception as e:
        logger.error(f"Error in /thread command: {e}")
        await message.reply_text(
            "❌ An error occurred while setting the thread ID.",
            reply_to_message_id=message.message_id,
        )


def main() -> None:
    """Start the bot and the FastAPI server."""
    from api.server import run_server as run_fastapi_server, set_bot_token

    if DEBUG_MODE:
        # Use test environment endpoints when in debug mode
        # Format: https://api.telegram.org/bot<token>/test/METHOD_NAME
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .base_url("https://api.telegram.org/bot")
            .base_file_url("https://api.telegram.org/file/bot")
            .concurrent_updates(True)
            .build()
        )
        # Override the bot's base_url to include /test/ for test environment
        application.bot._base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/test"
        application.bot._base_file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/test"
        logger.info("🧪 Running in DEBUG mode with test environment endpoints")
        logger.info(f"🔗 API Base URL: {application.bot._base_url}")
    else:
        # Use local Telegram Bot API server in production
        api_base_url = "http://localhost:8081"
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .base_url(f"{api_base_url}/bot")
            .base_file_url(f"{api_base_url}/file/bot")
            .local_mode(True)
            .concurrent_updates(True)
            .build()
        )
        logger.info("🚀 Running in PRODUCTION mode with local Telegram Bot API server")
        logger.info(f"🔗 API Base URL: {api_base_url}")

    # Share bot token with the server
    set_bot_token(TELEGRAM_TOKEN, DEBUG_MODE)
    logger.info("🤝 Bot token shared with FastAPI server")

    # Start FastAPI server in a separate thread
    fastapi_thread = threading.Thread(target=run_fastapi_server)
    fastapi_thread.daemon = True
    fastapi_thread.start()
    logger.info("🚀 Starting FastAPI server on port 8000")

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(
        MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/profile\b"), profile)
    )
    application.add_handler(CommandHandler("delete", delete_character))
    application.add_handler(CommandHandler("enroll", enroll))
    application.add_handler(CommandHandler("unenroll", unenroll))
    application.add_handler(CommandHandler("casino", casino))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("roll", roll))
    application.add_handler(CommandHandler("recycle", recycle))
    application.add_handler(CommandHandler("burn", burn))
    application.add_handler(CommandHandler("refresh", refresh))
    application.add_handler(CommandHandler("collection", collection))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("trade", trade))
    application.add_handler(CommandHandler("lock", lock_card_command))
    application.add_handler(CommandHandler("spins", spins))
    application.add_handler(CommandHandler("reload", reload))
    application.add_handler(CommandHandler("set_thread", set_thread))
    application.add_handler(CallbackQueryHandler(claim_card, pattern="^claim_"))
    application.add_handler(CallbackQueryHandler(handle_lock, pattern="^lock_"))
    application.add_handler(CallbackQueryHandler(handle_lock_card_confirm, pattern="^lockcard_"))
    application.add_handler(CallbackQueryHandler(handle_recycle_callback, pattern="^recycle_"))
    application.add_handler(CallbackQueryHandler(handle_burn_callback, pattern="^burn_"))
    application.add_handler(CallbackQueryHandler(handle_refresh_callback, pattern="^refresh_"))
    application.add_handler(CallbackQueryHandler(handle_reroll, pattern="^reroll_"))
    application.add_handler(
        CallbackQueryHandler(handle_collection_navigation, pattern="^collection_(prev|next|close)_")
    )
    application.add_handler(CallbackQueryHandler(accept_trade, pattern="^trade_accept_"))
    application.add_handler(CallbackQueryHandler(reject_trade, pattern="^trade_reject_"))

    application.run_polling()


if __name__ == "__main__":
    main()
