import asyncio
import logging
import os
import random
import sys
import base64
import datetime
import json
import threading
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
    BASE_IMAGE_PATH,
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
from utils import gemini, database

# Load environment variables
load_dotenv()

gemini_util = gemini.GeminiUtil()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

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


def get_downgraded_rarity(current_rarity):
    """Return a rarity one level lower than the current rarity."""
    rarity_order = ["Common", "Rare", "Epic", "Legendary"]
    try:
        current_index = rarity_order.index(current_rarity)
        if current_index > 0:
            return rarity_order[current_index - 1]
        else:
            return "Common"  # If already Common, stay Common
    except ValueError:
        return "Common"  # Default to Common if rarity not found


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
        if not await asyncio.to_thread(database.can_roll, user.id):
            hours, minutes = get_time_until_next_roll(user.id)
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
        base_images = [f for f in os.listdir(BASE_IMAGE_PATH) if not f.startswith(".")]
        if not base_images:
            await update.message.reply_text(
                "No base images found to create a card.",
                reply_to_message_id=update.message.message_id,
            )
            if not DEBUG_MODE:
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
            if not DEBUG_MODE:
                await context.bot.set_message_reaction(
                    chat_id=update.effective_chat.id,
                    message_id=update.message.message_id,
                    reaction=[],
                )
            return

        card_id = await asyncio.to_thread(database.add_card, base_name, modifier, rarity, image_b64)

        if not DEBUG_MODE:
            await asyncio.to_thread(database.record_roll, user.id)

        keyboard = [
            [InlineKeyboardButton("Claim", callback_data=f"claim_{card_id}")],
            [InlineKeyboardButton("Reroll", callback_data=f"reroll_{card_id}_{user.id}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        caption = (
            CARD_CAPTION_BASE.format(card_id=card_id, card_title=card_title, rarity=rarity)
            + CARD_STATUS_UNCLAIMED
        )

        message = await update.message.reply_photo(
            photo=base64.b64decode(image_b64),
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=update.message.message_id,
        )

        # Save the file_id returned by Telegram for future use
        if message.photo:
            file_id = message.photo[-1].file_id  # Get the largest photo size
            await asyncio.to_thread(database.update_card_file_id, card_id, file_id)

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


async def handle_reroll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle reroll button click."""
    query = update.callback_query

    data_parts = query.data.split("_")
    card_id = int(data_parts[1])
    original_roller_id = int(data_parts[2])

    user = query.from_user

    # Check if the user clicking is the original roller
    if user.id != original_roller_id:
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

    try:
        context.bot_data["rerolling_cards"].add(card_id)
        await query.edit_message_caption(caption=CARD_STATUS_REROLLING, parse_mode=ParseMode.HTML)

        # Generate new card with downgraded rarity
        base_images = [f for f in os.listdir(BASE_IMAGE_PATH) if not f.startswith(".")]
        if not base_images:
            logger.error("Base images not found.")
            await query.answer("Error: base images not found.", show_alert=True)
            # Restore original message
            await query.edit_message_caption(
                caption=query.message.caption, reply_markup=query.message.reply_markup
            )
            return

        chosen_file_name = random.choice(base_images)
        base_name = os.path.splitext(chosen_file_name)[0]

        downgraded_rarity = get_downgraded_rarity(original_card.rarity)
        modifier = random.choice(RARITIES[downgraded_rarity]["modifiers"])

        card_title = f"{modifier} {base_name}"

        base_image_path = os.path.join(BASE_IMAGE_PATH, chosen_file_name)
        image_b64 = await asyncio.to_thread(
            gemini_util.generate_image, base_name, modifier, downgraded_rarity, base_image_path
        )

        if not image_b64:
            await query.answer("Sorry, couldn't generate a new image!", show_alert=True)
            # Restore original message
            await query.edit_message_caption(
                caption=query.message.caption, reply_markup=query.message.reply_markup
            )
            return

        # Add new card to database
        new_card_id = await asyncio.to_thread(
            database.add_card, base_name, modifier, downgraded_rarity, image_b64
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
                card_id=new_card_id, card_title=card_title, rarity=downgraded_rarity
            )
            + CARD_STATUS_UNCLAIMED
            + CARD_STATUS_REROLLED.format(
                original_rarity=original_card.rarity, downgraded_rarity=downgraded_rarity
            )
        )

        # Update message with new image and caption
        message = await query.edit_message_media(
            media=InputMediaPhoto(
                media=base64.b64decode(image_b64), caption=caption, parse_mode=ParseMode.HTML
            ),
            reply_markup=reply_markup,
        )

        # Save the file_id returned by Telegram for future use
        if message.photo:
            file_id = message.photo[-1].file_id
            await asyncio.to_thread(database.update_card_file_id, new_card_id, file_id)

        await query.answer(f"Rerolled! New rarity: {downgraded_rarity}")
    except Exception as e:
        logger.error(f"Error in reroll: {e}")
        await query.answer("An error occurred during reroll!", show_alert=True)
    finally:
        context.bot_data["rerolling_cards"].discard(card_id)


async def claim_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle claim button click."""
    query = update.callback_query
    data = query.data
    card_id = int(data.split("_")[1])

    if "rerolling_cards" in context.bot_data and card_id in context.bot_data["rerolling_cards"]:
        await query.answer("The card is being rerolled, please wait.", show_alert=True)
        return

    user = query.from_user

    is_successful_claim = await asyncio.to_thread(database.claim_card, card_id, user.username)
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
                [f"@{u.strip()}" for u in attempted_by.split(",") if u.strip()]
            )
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

    await query.edit_message_caption(
        caption=caption, reply_markup=new_reply_markup, parse_mode=ParseMode.HTML
    )


async def collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display user's card collection."""
    user = update.effective_user
    cards = await asyncio.to_thread(database.get_user_collection, user.username)

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
            if update.callback_query.from_user.id != original_user_id:
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

    card = cards[current_index]
    card_title = f"{card.modifier} {card.base_name}"
    rarity = card.rarity

    caption = COLLECTION_CAPTION.format(
        card_id=card.id,
        card_title=card_title,
        rarity=rarity,
        current_index=current_index + 1,
        total_cards=len(cards),
        username=user.username,
    )

    keyboard = []
    if len(cards) > 1:
        keyboard.append(
            [
                InlineKeyboardButton("Prev", callback_data=f"collection_prev_{user.id}"),
                InlineKeyboardButton("Next", callback_data=f"collection_next_{user.id}"),
            ]
        )

    # Add miniapp button
    if DEBUG_MODE:
        # In debug mode, use WebApp with DEBUG_MINIAPP_URL
        miniapp_url = os.getenv("DEBUG_MINIAPP_URL")
        if miniapp_url and update.effective_chat.type == ChatType.PRIVATE:
            # Try to import WebApp, fallback to URL button if not available
            try:
                from telegram import WebApp

                keyboard.append(
                    [InlineKeyboardButton("View in the app!", web_app=WebApp(url=miniapp_url))]
                )
            except ImportError:
                # Fallback to regular URL button if WebApp is not available
                keyboard.append([InlineKeyboardButton("View in the app!", url=miniapp_url)])
        elif miniapp_url:
            # In group chats, use regular URL button
            keyboard.append([InlineKeyboardButton("View in browser", url=miniapp_url)])
    else:
        # In production mode, use link button with bot URL and username as start parameter
        bot_url = f"https://t.me/CrunchyGherkinsGachaBot/collection?startapp={user.username}"
        keyboard.append([InlineKeyboardButton("View in the app!", url=bot_url)])

    keyboard.append([InlineKeyboardButton("Close", callback_data=f"collection_close_{user.id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    media = card.get_media()

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


async def trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiate a card trade."""
    user1 = update.effective_user

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

    if card1.owner != user1.username:
        await update.message.reply_text(
            f"You do not own card <b>{card1.title()}</b>.", parse_mode=ParseMode.HTML
        )
        return

    if card2.owner == user1.username:
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
            user1_username=user1.username,
            card1_title=card1.title(),
            user2_username=user2_username,
            card2_title=card2.title(),
        ),
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )


async def reject_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle trade rejection."""
    query = update.callback_query

    _, _, card_id1_str, card_id2_str = query.data.split("_")
    card_id1 = int(card_id1_str)
    card_id2 = int(card_id2_str)

    user_who_clicked = query.from_user

    card1 = await asyncio.to_thread(database.get_card, card_id1)
    card2 = await asyncio.to_thread(database.get_card, card_id2)

    if not card1 or not card2:
        await query.answer()
        await query.edit_message_text("Trade failed: one of the cards no longer exists.")
        return

    user1_username = card1.owner
    user2_username = card2.owner

    if not DEBUG_MODE and user_who_clicked.username != user2_username:
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


async def accept_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle trade acceptance."""
    query = update.callback_query

    _, _, card_id1_str, card_id2_str = query.data.split("_")
    card_id1 = int(card_id1_str)
    card_id2 = int(card_id2_str)

    user_who_clicked = query.from_user

    card1 = await asyncio.to_thread(database.get_card, card_id1)
    card2 = await asyncio.to_thread(database.get_card, card_id2)

    if not card1 or not card2:
        await query.answer()
        await query.edit_message_text("Trade failed: one of the cards no longer exists.")
        return

    user1_username = card1.owner
    user2_username = card2.owner

    if not DEBUG_MODE and user_who_clicked.username != user2_username:
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


async def reload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reload command - clears all file_ids. Only accessible to admin."""
    user = update.effective_user

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
    from api.server import run_server as run_fastapi_server

    # Start FastAPI server in a separate thread
    fastapi_thread = threading.Thread(target=run_fastapi_server)
    fastapi_thread.daemon = True
    fastapi_thread.start()
    logger.info("🚀 Starting FastAPI server on port 8000")

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
