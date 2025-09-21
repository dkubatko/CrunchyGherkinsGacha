import asyncio
import logging
import os
import random
import sys
import base64
import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    ReactionTypeEmoji,
)
from telegram.constants import ParseMode, ChatType
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

from settings.constants import (
    RARITIES,
    IMAGE_GENERATOR_INSTRUCTION,
    REACTION_IN_PROGRESS,
)
from utils import database, gemini

# Load environment variables
load_dotenv()

gemini_util = gemini.GeminiUtil()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BASE_IMAGE_PATH = "data/base_images"
DEBUG_MODE = "--debug" in sys.argv

# Use debug token when in debug mode, otherwise use production token
if DEBUG_MODE:
    TELEGRAM_TOKEN = os.getenv("DEBUG_TELEGRAM_AUTH_TOKEN")
else:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_AUTH_TOKEN")


def get_random_rarity():
    """Return a rarity based on chance."""
    rarity_list = list(RARITIES.keys())
    weights = [RARITIES[rarity]["weight"] for rarity in rarity_list]
    return random.choices(rarity_list, weights=weights, k=1)[0]


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


async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Roll a new card."""
    user = update.effective_user
    if update.effective_chat.type == ChatType.PRIVATE and not DEBUG_MODE:
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
                text=f"@{user.username} attempted to roll in a private chat.",
            )
        return

    await context.bot.set_message_reaction(
        chat_id=update.effective_chat.id,
        message_id=update.message.message_id,
        reaction=[ReactionTypeEmoji(REACTION_IN_PROGRESS)],
    )
    if not DEBUG_MODE:
        if not await asyncio.to_thread(database.can_roll, user.id):
            hours, minutes = get_time_until_next_roll(user.id)
            await update.message.reply_text(
                f"You have already rolled for a card. Next roll in {hours} hours {minutes} minutes.",
                reply_to_message_id=update.message.message_id,
            )
            await context.bot.set_message_reaction(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                reaction=[],
            )
            return

    try:
        base_images = [f for f in os.listdir(BASE_IMAGE_PATH) if not f.startswith(".")]
        if not base_images:
            await update.message.reply_text(
                "No base images found to create a card.",
                reply_to_message_id=update.message.message_id,
            )
            await context.bot.set_message_reaction(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                reaction=[],
            )
            return

        chosen_file_name = random.choice(base_images)
        base_name = os.path.splitext(chosen_file_name)[0]

        rarity = get_random_rarity()
        modifier = random.choice(RARITIES[rarity]["modifiers"])

        card_title = f"{modifier} {base_name}"

        base_image_path = os.path.join(BASE_IMAGE_PATH, chosen_file_name)
        image_b64 = await asyncio.to_thread(
            gemini_util.generate_image, base_name, modifier, rarity, base_image_path
        )

        if not image_b64:
            await update.message.reply_text(
                "Sorry, I couldn't generate an image at the moment.",
                reply_to_message_id=update.message.message_id,
            )
            await context.bot.set_message_reaction(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                reaction=[],
            )
            return

        card_id = await asyncio.to_thread(database.add_card, base_name, modifier, rarity, image_b64)

        if not DEBUG_MODE:
            await asyncio.to_thread(database.record_roll, user.id)

        keyboard = [[InlineKeyboardButton("Claim", callback_data=f"claim_{card_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        caption = f"<b>{card_title}</b>\nRarity: <b>{rarity}</b>\n\n<i>Unclaimed</i>"

        await update.message.reply_photo(
            photo=base64.b64decode(image_b64),
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=update.message.message_id,
        )

    except Exception as e:
        logger.error(f"Error in /roll: {e}")
        await update.message.reply_text(
            "An error occurred while rolling for a card.",
            reply_to_message_id=update.message.message_id,
        )
    finally:
        await context.bot.set_message_reaction(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
            reaction=[],
        )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button clicks."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("claim_"):
        card_id = int(data.split("_")[1])
        user = query.from_user

        if await asyncio.to_thread(database.claim_card, card_id, user.username):
            card = await asyncio.to_thread(database.get_card, card_id)
            card_title = f"{card[2]} {card[1]}"
            rarity = card[3]

            caption = f"<b>{card_title}</b>\nRarity: <b>{rarity}</b>\n\n<i>Claimed by @{user.username}</i>"

            await query.edit_message_caption(
                caption=caption, reply_markup=None, parse_mode=ParseMode.HTML
            )
        else:
            # Card already claimed, update caption to show attempted users
            card = await asyncio.to_thread(database.get_card, card_id)
            card_title = f"{card[2]} {card[1]}"
            rarity = card[3]
            owner = card[4]
            attempted_by = card[6] if len(card) > 6 and card[6] else ""

            caption = f"<b>{card_title}</b>\n<b>{rarity}</b>\n\n<i>Claimed by @{owner}</i>"
            if attempted_by:
                attempted_users = ", ".join(
                    [f"@{u.strip()}" for u in attempted_by.split(",") if u.strip()]
                )
                caption += f"\n<i>Attempted by: {attempted_users}</i>"

            await query.edit_message_caption(
                caption=caption, reply_markup=None, parse_mode=ParseMode.HTML
            )


async def collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display user's card collection."""
    user = update.effective_user
    cards = await asyncio.to_thread(database.get_user_collection, user.username)

    if not cards:
        await update.message.reply_text(
            "You don't own any cards yet. Use /roll to get your first card!",
            reply_to_message_id=update.message.message_id,
        )
        return

    current_index = context.user_data.get("collection_index", 0)

    if update.callback_query:
        if "prev" in update.callback_query.data:
            current_index = (current_index - 1) % len(cards)
        elif "next" in update.callback_query.data:
            current_index = (current_index + 1) % len(cards)

    context.user_data["collection_index"] = current_index

    card = cards[current_index]
    card_title = f"{card[2]} {card[1]}"
    rarity = card[3]
    image_b64 = card[5]

    caption = (
        f"<b>{card_title}</b>\n"
        f"Rarity: <b>{rarity}</b>\n\n"
        f"<i>Showing {current_index + 1}/{len(cards)} owned by @{user.username}</i>"
    )

    keyboard = []
    if len(cards) > 1:
        keyboard.append(
            [
                InlineKeyboardButton("Prev", callback_data="collection_prev"),
                InlineKeyboardButton("Next", callback_data="collection_next"),
            ]
        )
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_media(
            media=InputMediaPhoto(media=base64.b64decode(image_b64), caption=caption),
            reply_markup=reply_markup,
        )
        await update.callback_query.edit_message_caption(
            caption=caption, reply_markup=reply_markup, parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_photo(
            photo=base64.b64decode(image_b64),
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=update.message.message_id,
        )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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


def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()

    application.add_handler(CommandHandler("roll", roll))
    application.add_handler(CommandHandler("collection", collection))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CallbackQueryHandler(button, pattern="^claim_"))
    application.add_handler(CallbackQueryHandler(collection, pattern="^collection_"))

    application.run_polling()


if __name__ == "__main__":
    main()
