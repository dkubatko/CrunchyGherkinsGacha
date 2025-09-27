import asyncio
import logging
import os
import sys
import base64
import datetime
import html
import json
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
    RECYCLE_ALLOWED_RARITIES,
    RECYCLE_UPGRADE_MAP,
    RECYCLE_BURN_COUNT,
    RECYCLE_MINIMUM_REQUIRED,
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
)
from utils import gemini, database, rolling
from utils.decorators import verify_user, verify_user_in_chat
from utils.rolled_card import RolledCardManager

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

# Use debug token when in debug mode, otherwise use production token
if DEBUG_MODE:
    TELEGRAM_TOKEN = os.getenv("DEBUG_TELEGRAM_AUTH_TOKEN")
else:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_AUTH_TOKEN")

TOKEN_PREFIX = "tg1_"


def encode_miniapp_token(user_id, chat_id=None):
    raw_token = f"{user_id}" if not chat_id else f"{user_id}.{chat_id}"
    encoded = base64.urlsafe_b64encode(raw_token.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{TOKEN_PREFIX}{encoded}"


def log_card_generation(generated_card, context="card generation"):
    """Log details about a generated card including its source."""
    source_type = "unknown"
    source_info = "unknown"

    if generated_card.source_user:
        source_type = "User"
        source_info = (
            f"{generated_card.source_user.display_name} ({generated_card.source_user.user_id})"
        )
    elif generated_card.source_character:
        source_type = "Character"
        source_info = (
            f"{generated_card.source_character.name} ({generated_card.source_character.id})"
        )

    logger.info(
        f"Generating card for {context}: {source_type} {source_info} -> ({generated_card.rarity}) {generated_card.modifier} {generated_card.base_name}"
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
    """Update the user's display name and profile image in DM, or add a character in group chats."""

    message = update.message
    user = update.effective_user

    if not message or not user:
        return

    # Check if it's a group chat or DM
    if update.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        # Group chat - add character functionality (admin only)
        admin_username = os.getenv("BOT_ADMIN")

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
                "Usage: /profile <character_name> (attach a photo with the command)."
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

        chat_id = str(update.effective_chat.id)
        character_id = await asyncio.to_thread(
            database.add_character, chat_id, character_name, image_b64
        )

        await message.reply_text(
            f"Character '{character_name}' added with ID {character_id}! They will now be used for card generation."
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

    if len(parts) < 2 or not parts[1].strip():
        await message.reply_text(
            "Usage: /profile <display_name> (attach a photo with the command)."
        )
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

    await asyncio.to_thread(database.upsert_user, user.id, user.username, None, None)
    await asyncio.to_thread(database.update_user_profile, user.id, display_name, image_b64)

    await message.reply_text("Profile updated! Your new display name and image are saved.")


async def delete_character(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete characters by name (case-insensitive). Admin only."""

    message = update.message
    user = update.effective_user

    if not message or not user:
        return

    # Restrict to admin only
    admin_username = os.getenv("BOT_ADMIN")

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
        group_chat_id = os.getenv("GROUP_CHAT_ID")
        if group_chat_id:
            await context.bot.send_message(
                chat_id=group_chat_id,
                text=f"@{user.username} attempted to roll in a private chat. 🐀",
            )
        return

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

    try:
        generated_card = await asyncio.to_thread(
            rolling.generate_card_for_chat,
            chat_id_str,
            gemini_util,
        )

        # Log the card generation details
        log_card_generation(generated_card, "roll")

        card_id = await asyncio.to_thread(
            database.add_card,
            generated_card.base_name,
            generated_card.modifier,
            generated_card.rarity,
            generated_card.image_b64,
            update.effective_chat.id,
        )

        if not DEBUG_MODE:
            await asyncio.to_thread(database.record_roll, user.user_id, chat_id_str)

        # Give the user 1 claim point for successfully rolling
        await asyncio.to_thread(database.increment_claim_balance, user.user_id, chat_id_str)

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
        if message.photo:
            file_id = message.photo[-1].file_id  # Get the largest photo size
            await asyncio.to_thread(database.update_card_file_id, card_id, file_id)

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
    chat_id_str = str(chat.id)

    cards = await asyncio.to_thread(
        database.get_user_cards_by_rarity,
        user.user_id,
        user.username,
        rarity_name,
        chat_id_str,
        RECYCLE_MINIMUM_REQUIRED,
    )

    if len(cards) < RECYCLE_MINIMUM_REQUIRED:
        await message.reply_text(
            RECYCLE_INSUFFICIENT_CARDS_MESSAGE.format(
                required=RECYCLE_MINIMUM_REQUIRED,
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
            burn_count=RECYCLE_BURN_COUNT,
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
        await query.answer(RECYCLE_NOT_YOURS_MESSAGE, show_alert=True)
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

    try:
        cards = await asyncio.to_thread(
            database.get_user_cards_by_rarity,
            user.user_id,
            user.username,
            rarity_name,
            str(chat_id),
            RECYCLE_MINIMUM_REQUIRED,
        )

        if len(cards) < RECYCLE_MINIMUM_REQUIRED:
            await query.answer(RECYCLE_FAILURE_NOT_ENOUGH_CARDS, show_alert=True)
            try:
                await query.edit_message_text(RECYCLE_FAILURE_NOT_ENOUGH_CARDS)
            except Exception:
                pass
            return

        cards_to_burn = cards[:RECYCLE_BURN_COUNT]
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
            database.add_card,
            generated_card.base_name,
            generated_card.modifier,
            generated_card.rarity,
            generated_card.image_b64,
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

        if message and message.photo:
            file_id = message.photo[-1].file_id
            await asyncio.to_thread(database.update_card_file_id, new_card_id, file_id)

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
        )

        # Log the card generation details
        log_card_generation(generated_card, "reroll")

        # Add new card to database
        new_card_chat_id = active_card.chat_id or (query.message.chat_id if query.message else None)
        new_card_id = await asyncio.to_thread(
            database.add_card,
            generated_card.base_name,
            generated_card.modifier,
            generated_card.rarity,
            generated_card.image_b64,
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
        if message.photo:
            file_id = message.photo[-1].file_id
            await asyncio.to_thread(database.update_card_file_id, new_card_id, file_id)

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

    # Check if the person trying to lock is the owner of the card
    if not rolled_card_manager.can_user_lock(user.user_id, user.username):
        await query.answer("Only the owner of the card can lock it!", show_alert=True)
        return

    chat = update.effective_chat
    chat_id = str(chat.id) if chat else None

    # Check if this is the original roller
    is_original_roller = rolled_card_manager.rolled_card.original_roller_id == user.user_id

    if not is_original_roller:
        # Not the original roller - need to consume a claim point to prevent rerolling
        remaining_balance = await asyncio.to_thread(
            database.reduce_claim_points, user.user_id, chat_id, 1
        )

        if remaining_balance is None:
            # Get current balance for error message
            current_balance = await asyncio.to_thread(
                database.get_claim_balance, user.user_id, chat_id
            )
            await query.answer(
                f"Not enough claim points!\n\nBalance: {current_balance}",
                show_alert=True,
            )
            return

        await query.answer(
            f"Card locked from re-rolling!\n\nBalance: {remaining_balance}",
            show_alert=True,
        )
    else:
        # Original roller - no claim point needed since they can't reroll their own claimed card anyway
        await query.answer("Card locked from re-rolling!", show_alert=True)

    # Set the card as locked
    rolled_card_manager.set_locked(True)

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
        RolledCardManager.claim,
        rolled_card_manager,
        user.username,
        user.user_id,
        chat_id,
    )

    if claim_result.status is database.ClaimStatus.INSUFFICIENT_BALANCE:
        balance_value = claim_result.balance if claim_result.balance is not None else 0
        await query.answer(
            (f"Not enough claim points!\n\nBalance: {balance_value}"),
            show_alert=True,
        )
        return

    card = rolled_card_manager.card
    card_title = f"{card.modifier} {card.base_name}"

    if claim_result.status is database.ClaimStatus.SUCCESS:
        if claim_result.balance is not None:
            await query.answer(
                f"Card {card_title} claimed!\n\nRemaining balance: {claim_result.balance}.",
                show_alert=True,
            )
        else:
            await query.answer(f"Card {card_title} claimed!", show_alert=True)
    else:
        # Card already claimed - check if it's owned by the same user
        owner = card.owner
        if owner == user.username:
            # Show success message with current balance for user's own card
            if chat_id and user.user_id:
                current_balance = await asyncio.to_thread(
                    database.get_claim_balance, user.user_id, chat_id
                )
                await query.answer(
                    f"Card {card_title} claimed!\n\nRemaining balance: {current_balance}.",
                    show_alert=True,
                )
            else:
                await query.answer(f"Card {card_title} claimed!", show_alert=True)
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

    if target_user_id == user.user_id:
        response_text = f"You have {balance_value} claim {point_label} available in this chat."
        if balance_value == 0:
            response_text += "\n\nUse /roll to get a claim point!"
    else:
        handle = f"@{display_username}" if display_username else str(target_user_id)
        response_text = f"{handle} has {balance_value} claim {point_label} available in this chat."

    if message:
        await message.reply_text(
            response_text,
            reply_to_message_id=getattr(message, "message_id", None),
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
    card_title = f"{card.modifier} {card.base_name}"
    rarity = card.rarity

    caption = COLLECTION_CAPTION.format(
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
        token = encode_miniapp_token(viewed_user_id, chat_id_filter)

        if DEBUG_MODE:
            # In debug mode, use direct URL with v parameter
            app_url = f"{miniapp_url}?v={token}"
        else:
            # In production mode, use direct URL with startapp parameter
            # This works in both group chats and private chats
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
    card_title = f"{card.modifier} {card.base_name}"
    rarity = card.rarity

    caption = COLLECTION_CAPTION.format(
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
        balance_line = f"{balance_value} claim {point_label}"
    else:
        balance_line = "unknown (no linked user ID)"

    handle_display = f"@{username}" if username else "unknown"

    return (
        f"{handle_display}: {user_stats['owned']} / {user_stats['total']} cards\n"
        f"L: {user_stats['rarities']['Legendary']}, "
        f"E: {user_stats['rarities']['Epic']}, "
        f"R: {user_stats['rarities']['Rare']}, "
        f"C: {user_stats['rarities']['Common']}\n"
        f"Balance: {balance_line}"
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

    keyboard = [
        [
            InlineKeyboardButton("Accept", callback_data=f"trade_accept_{card_id1}_{card_id2}"),
            InlineKeyboardButton("Reject", callback_data=f"trade_reject_{card_id1}_{card_id2}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        TRADE_REQUEST_MESSAGE.format(
            user1_username=user.username,
            card1_title=card1.title(),
            user2_username=user2_username,
            card2_title=card2.title(),
        ),
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )


@verify_user_in_chat
async def reject_trade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Handle trade rejection."""
    query = update.callback_query

    _, _, card_id1_str, card_id2_str = query.data.split("_")
    card_id1 = int(card_id1_str)
    card_id2 = int(card_id2_str)

    card1 = await asyncio.to_thread(database.get_card, card_id1)
    card2 = await asyncio.to_thread(database.get_card, card_id2)

    if not card1 or not card2:
        await query.answer()
        await query.edit_message_text("Trade failed: one of the cards no longer exists.")
        return

    user1_username = card1.owner
    user2_username = card2.owner

    if not DEBUG_MODE and user.username != user2_username:
        await query.answer("You are not the owner of the card being traded for.", show_alert=True)
        return

    await query.edit_message_text(
        TRADE_REJECTED_MESSAGE.format(
            user1_username=user1_username,
            card1_title=card1.title(),
            user2_username=user2_username,
            card2_title=card2.title(),
        ),
        parse_mode=ParseMode.HTML,
    )
    await query.answer()


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
        await query.edit_message_text("Trade failed: one of the cards no longer exists.")
        return

    user1_username = card1.owner
    user2_username = card2.owner

    if not DEBUG_MODE and user.username != user2_username:
        await query.answer("You are not the owner of the card being traded for.", show_alert=True)
        return

    success = await asyncio.to_thread(database.swap_card_owners, card_id1, card_id2)

    if success:
        await query.edit_message_text(
            TRADE_COMPLETE_MESSAGE.format(
                user1_username=user1_username,
                card1_title=card1.title(),
                user2_username=user2_username,
                card2_title=card2.title(),
            ),
            parse_mode=ParseMode.HTML,
        )
    else:
        await query.edit_message_text("Trade failed. Please try again.")

    await query.answer()


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
        application = Application.builder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()
        logger.info("🚀 Running in PRODUCTION mode")

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
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("roll", roll))
    application.add_handler(CommandHandler("recycle", recycle))
    application.add_handler(CommandHandler("collection", collection))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("trade", trade))
    application.add_handler(CommandHandler("reload", reload))
    application.add_handler(CallbackQueryHandler(claim_card, pattern="^claim_"))
    application.add_handler(CallbackQueryHandler(handle_lock, pattern="^lock_"))
    application.add_handler(CallbackQueryHandler(handle_recycle_callback, pattern="^recycle_"))
    application.add_handler(CallbackQueryHandler(handle_reroll, pattern="^reroll_"))
    application.add_handler(
        CallbackQueryHandler(handle_collection_navigation, pattern="^collection_(prev|next|close)_")
    )
    application.add_handler(CallbackQueryHandler(accept_trade, pattern="^trade_accept_"))
    application.add_handler(CallbackQueryHandler(reject_trade, pattern="^trade_reject_"))

    application.run_polling()


if __name__ == "__main__":
    main()
