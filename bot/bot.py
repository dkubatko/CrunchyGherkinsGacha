import asyncio
import logging
import os
import sys
import base64
import datetime
import json
import threading
import urllib.parse
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
    CARD_STATUS_ATTEMPTED,
    CARD_STATUS_REROLLING,
    CARD_STATUS_REROLLED,
    TRADE_REQUEST_MESSAGE,
    TRADE_COMPLETE_MESSAGE,
    TRADE_REJECTED_MESSAGE,
)
from utils import gemini, database, rolling
from utils.decorators import verify_user, verify_user_in_chat

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

GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")


def get_generation_chat_id(chat_id: int | str) -> str:
    """Return the chat id to use during image generation."""
    if DEBUG_MODE and GROUP_CHAT_ID:
        return str(GROUP_CHAT_ID)
    return str(chat_id)


def get_time_until_next_roll(user_id):
    """Calculate time until next roll (24 hours from last roll).
    Uses the same timezone as the database (system local time).
    """
    last_roll_time = database.get_last_roll_time(user_id)
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
    """Update the user's display name and profile image. DM-only."""

    message = update.message
    user = update.effective_user

    if not message or not user:
        return

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
    photo_bytes = await telegram_file.download_to_memory()
    image_b64 = base64.b64encode(bytes(photo_bytes)).decode("utf-8")

    await asyncio.to_thread(database.upsert_user, user.id, user.username, None, None)
    await asyncio.to_thread(database.update_user_profile, user.id, display_name, image_b64)

    await message.reply_text("Profile updated! Your new display name and image are saved.")


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
        if not await asyncio.to_thread(database.can_roll, user.user_id):
            hours, minutes = get_time_until_next_roll(user.user_id)
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
        chat_id_str = get_generation_chat_id(update.effective_chat.id)
        generated_card = await asyncio.to_thread(
            rolling.generate_card_for_chat,
            chat_id_str,
            gemini_util,
        )

        card_id = await asyncio.to_thread(
            database.add_card,
            generated_card.base_name,
            generated_card.modifier,
            generated_card.rarity,
            generated_card.image_b64,
            update.effective_chat.id,
        )

        if not DEBUG_MODE:
            await asyncio.to_thread(database.record_roll, user.user_id)

        keyboard = [
            [InlineKeyboardButton("Claim", callback_data=f"claim_{card_id}")],
            [InlineKeyboardButton("Reroll", callback_data=f"reroll_{card_id}_{user.user_id}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        caption = (
            CARD_CAPTION_BASE.format(
                card_id=card_id, card_title=generated_card.card_title, rarity=generated_card.rarity
            )
            + CARD_STATUS_UNCLAIMED
        )

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


@verify_user_in_chat
async def handle_reroll(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Handle reroll button click."""
    query = update.callback_query

    data_parts = query.data.split("_")
    card_id = int(data_parts[1])
    original_roller_id = int(data_parts[2])

    # Check if the user clicking is the original roller
    if user.user_id != original_roller_id:
        await query.answer("Only the original roller can reroll this card!", show_alert=True)
        return

    # Check if reroll time limit has expired
    reroll_expired = await asyncio.to_thread(database.is_reroll_expired, card_id)
    if reroll_expired:
        await query.answer("Reroll has expired", show_alert=True)

        # Remove reroll button from the message
        current_keyboard = query.message.reply_markup.inline_keyboard
        new_keyboard = []
        for row in current_keyboard:
            new_row = [button for button in row if not button.callback_data.startswith("reroll_")]
            if new_row:
                new_keyboard.append(new_row)

        new_reply_markup = InlineKeyboardMarkup(new_keyboard) if new_keyboard else None
        await query.edit_message_reply_markup(reply_markup=new_reply_markup)
        return

    # Get the original card
    original_card = await asyncio.to_thread(database.get_card, card_id)
    if not original_card:
        await query.answer("Card not found!", show_alert=True)
        return

    if "rerolling_cards" not in context.bot_data:
        context.bot_data["rerolling_cards"] = set()

    if card_id in context.bot_data["rerolling_cards"]:
        await query.answer("This card is already being rerolled.", show_alert=True)
        return

    original_caption = query.message.caption
    original_markup = query.message.reply_markup

    try:
        context.bot_data["rerolling_cards"].add(card_id)
        await query.edit_message_caption(caption=CARD_STATUS_REROLLING, parse_mode=ParseMode.HTML)

        downgraded_rarity = rolling.get_downgraded_rarity(original_card.rarity)
        chat_id_candidate = original_card.chat_id or query.message.chat_id
        chat_id_for_generation = get_generation_chat_id(chat_id_candidate)

        generated_card = await asyncio.to_thread(
            rolling.generate_card_for_chat,
            chat_id_for_generation,
            gemini_util,
            downgraded_rarity,
        )

        # Add new card to database
        new_card_chat_id = original_card.chat_id or query.message.chat_id
        new_card_id = await asyncio.to_thread(
            database.add_card,
            generated_card.base_name,
            generated_card.modifier,
            generated_card.rarity,
            generated_card.image_b64,
            new_card_chat_id,
        )

        # Delete the original card
        await asyncio.to_thread(database.delete_card, card_id)

        # Update the message with new card
        keyboard = [
            [InlineKeyboardButton("Claim", callback_data=f"claim_{new_card_id}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        caption = (
            CARD_CAPTION_BASE.format(
                card_id=new_card_id,
                card_title=generated_card.card_title,
                rarity=generated_card.rarity,
            )
            + CARD_STATUS_UNCLAIMED
            + CARD_STATUS_REROLLED.format(
                original_rarity=original_card.rarity, downgraded_rarity=generated_card.rarity
            )
        )

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

        await query.answer(f"Rerolled! New rarity: {generated_card.rarity}")
    except rolling.NoEligibleUserError:
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
        await query.edit_message_caption(
            caption=original_caption,
            reply_markup=original_markup,
            parse_mode=ParseMode.HTML,
        )
        await query.answer("Sorry, couldn't generate a new image!", show_alert=True)
    except Exception as e:
        logger.error(f"Error in reroll: {e}")
        await query.answer("An error occurred during reroll!", show_alert=True)
    finally:
        context.bot_data["rerolling_cards"].discard(card_id)


@verify_user_in_chat
async def claim_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Handle claim button click."""
    query = update.callback_query
    data = query.data
    card_id = int(data.split("_")[1])

    if "rerolling_cards" in context.bot_data and card_id in context.bot_data["rerolling_cards"]:
        await query.answer("The card is being rerolled, please wait.", show_alert=True)
        return

    is_successful_claim = await asyncio.to_thread(
        database.claim_card, card_id, user.username, user.user_id
    )
    card = await asyncio.to_thread(database.get_card, card_id)
    card_title = f"{card.modifier} {card.base_name}"
    rarity = card.rarity

    if is_successful_claim:
        caption = CARD_CAPTION_BASE.format(
            card_id=card_id, card_title=card_title, rarity=rarity
        ) + CARD_STATUS_CLAIMED.format(username=user.username)
        await query.answer(f"Card {card_title} claimed!", show_alert=True)
    else:
        # Card already claimed, update caption to show attempted users
        owner = card.owner
        attempted_by = card.attempted_by if card.attempted_by else ""

        caption = CARD_CAPTION_BASE.format(
            card_id=card_id, card_title=card_title, rarity=rarity
        ) + CARD_STATUS_CLAIMED.format(username=owner)
        if attempted_by:
            attempted_users = ", ".join(
                [
                    f"@{u.strip()}"
                    for u in attempted_by.split(",")
                    if u.strip() and u.strip() != owner
                ]
            )
            if attempted_users:
                caption += CARD_STATUS_ATTEMPTED.format(users=attempted_users)
        await query.answer(f"Too late! Already claimed by @{owner}.", show_alert=True)

    # Keep other buttons, remove the claim button
    current_keyboard = query.message.reply_markup.inline_keyboard
    new_keyboard = []
    for row in current_keyboard:
        new_row = [button for button in row if not button.callback_data.startswith("claim_")]
        if new_row:
            new_keyboard.append(new_row)

    new_reply_markup = InlineKeyboardMarkup(new_keyboard) if new_keyboard else None

    try:
        await query.edit_message_caption(
            caption=caption, reply_markup=new_reply_markup, parse_mode=ParseMode.HTML
        )
    except Exception:
        # Silently ignore if message content is identical (Telegram BadRequest)
        pass


@verify_user
async def collection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Display user's card collection."""

    chat = update.effective_chat
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

    # Check if a username argument was provided
    if context.args and len(context.args) > 0:
        target_username = context.args[0].lstrip("@")  # Remove @ if present
        # Check if the target user exists by trying to get their collection
        target_cards = await asyncio.to_thread(database.get_user_collection, target_username)
        if not target_cards:
            await update.message.reply_text(
                f"@{target_username} doesn't exist or doesn't own any cards yet.",
                reply_to_message_id=update.message.message_id,
            )
            return
        cards = target_cards
        display_username = target_username
    else:
        # Default to current user's collection
        cards = await asyncio.to_thread(database.get_user_collection, user.username)
        display_username = user.username

        if not cards and not update.callback_query:
            await update.message.reply_text(
                "You don't own any cards yet. Use /roll to get your first card!",
                reply_to_message_id=update.message.message_id,
            )
            return

    current_index = context.user_data.get("collection_index", 0)

    if update.callback_query:
        # Check if the user clicking the button is the same user who initiated the collection
        callback_data_parts = update.callback_query.data.split("_")
        if len(callback_data_parts) >= 3:
            original_user_id = int(callback_data_parts[2])
            if user.user_id != original_user_id:
                await update.callback_query.answer(
                    "You can only navigate your own collection!", show_alert=True
                )
                return

        if "prev" in update.callback_query.data:
            current_index = (current_index - 1) % len(cards)
        elif "next" in update.callback_query.data:
            current_index = (current_index + 1) % len(cards)
        elif "close" in update.callback_query.data:
            await update.callback_query.delete_message()
            await update.callback_query.answer()
            return

    context.user_data["collection_index"] = current_index

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
                InlineKeyboardButton("Prev", callback_data=f"collection_prev_{user.user_id}"),
                InlineKeyboardButton("Next", callback_data=f"collection_next_{user.user_id}"),
            ]
        )

    # Add miniapp button
    miniapp_url = os.getenv("DEBUG_MINIAPP_URL" if DEBUG_MODE else "MINIAPP_URL")
    if miniapp_url:
        if DEBUG_MODE:
            # In debug mode, use WebApp with direct URL parameter
            app_url = f"{miniapp_url}?v={urllib.parse.quote(display_username)}"
            keyboard.append(
                [InlineKeyboardButton("View in the app!", web_app=WebAppInfo(url=app_url))]
            )
        else:
            # In production mode, use inline button with URL and startapp parameter
            app_url = f"{miniapp_url}?startapp={urllib.parse.quote(display_username)}"
            keyboard.append([InlineKeyboardButton("View in the app!", url=app_url)])

    keyboard.append(
        [InlineKeyboardButton("Close", callback_data=f"collection_close_{user.user_id}")]
    )
    reply_markup = InlineKeyboardMarkup(keyboard)

    media = card_with_image.get_media()

    if update.callback_query:
        # For callback queries (navigation)
        message = await update.callback_query.edit_message_media(
            media=InputMediaPhoto(media=media, caption="Loading..."),
            reply_markup=reply_markup,
        )
        await update.callback_query.edit_message_caption(
            caption=caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML
        )
        # Always update file_id with what Telegram returns
        if message and message.photo:
            new_file_id = message.photo[-1].file_id
            await asyncio.to_thread(database.update_card_file_id, card.id, new_file_id)
        await update.callback_query.answer()
    else:
        # For new collection requests
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


@verify_user_in_chat
async def stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: database.User,
) -> None:
    """Display stats for all users."""
    users = await asyncio.to_thread(database.get_all_users_with_cards)

    if not users:
        await update.message.reply_text(
            "No users have claimed any cards yet.", reply_to_message_id=update.message.message_id
        )
        return

    message_parts = []
    for username in users:
        user_stats = await asyncio.to_thread(database.get_user_stats, username)
        user_line = (
            f"@{username}: {user_stats['owned']} / {user_stats['total']} cards\n"
            f"L: {user_stats['rarities']['Legendary']}, E: {user_stats['rarities']['Epic']}, "
            f"R: {user_stats['rarities']['Rare']}, C: {user_stats['rarities']['Common']}"
        )
        message_parts.append(user_line)

    message = "\n\n".join(message_parts)

    await update.message.reply_text(message, reply_to_message_id=update.message.message_id)


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
    application.add_handler(CommandHandler("enroll", enroll))
    application.add_handler(CommandHandler("roll", roll))
    application.add_handler(CommandHandler("collection", collection))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("trade", trade))
    application.add_handler(CommandHandler("reload", reload))
    application.add_handler(CallbackQueryHandler(claim_card, pattern="^claim_"))
    application.add_handler(CallbackQueryHandler(handle_reroll, pattern="^reroll_"))
    application.add_handler(CallbackQueryHandler(collection, pattern="^collection_"))
    application.add_handler(CallbackQueryHandler(accept_trade, pattern="^trade_accept_"))
    application.add_handler(CallbackQueryHandler(reject_trade, pattern="^trade_reject_"))

    application.run_polling()


if __name__ == "__main__":
    main()
