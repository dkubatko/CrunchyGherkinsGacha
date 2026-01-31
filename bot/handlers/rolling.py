"""
Rolling-related command handlers.

This module contains handlers for rolling new cards and rerolling existing cards.
"""

import asyncio
import base64
import logging

from telegram import Update, InputMediaPhoto, ReactionTypeEmoji
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from config import DEBUG_MODE, MAX_BOT_IMAGE_RETRIES, gemini_util
from handlers.helpers import (
    get_time_until_next_roll,
    log_card_generation,
    save_card_file_id_from_message,
)
from settings.constants import (
    REACTION_IN_PROGRESS,
    CARD_CAPTION_BASE,
    get_claim_cost,
)
from utils import rolling
from utils.services import (
    card_service,
    claim_service,
    rolled_card_service,
    roll_service,
    event_service,
)
from utils.schemas import User
from utils.decorators import verify_user_in_chat, prevent_concurrency
from utils.rolled_card import RolledCardManager
from utils.events import EventType, RollOutcome, RerollOutcome
from api.background_tasks import process_claim_countdown

logger = logging.getLogger(__name__)


@verify_user_in_chat
async def roll(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
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
            if not await asyncio.to_thread(roll_service.can_roll, user.user_id, chat_id_str):
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
            source="roll",
        )

        # Log the card generation details
        log_card_generation(generated_card, "roll")

        card_id = await asyncio.to_thread(
            card_service.add_card_from_generated,
            generated_card,
            update.effective_chat.id,
        )

        # Award claim points based on the rolled card's rarity
        claim_reward = get_claim_cost(generated_card.rarity)
        await asyncio.to_thread(
            claim_service.increment_claim_balance,
            user.user_id,
            chat_id_str,
            claim_reward,
        )

        # Create rolled card entry to track state
        roll_id = await asyncio.to_thread(
            rolled_card_service.create_rolled_card, card_id, user.user_id
        )

        # Use RolledCardManager to generate pre-claim caption (no claim button yet)
        rolled_card_manager = RolledCardManager(roll_id)
        caption = rolled_card_manager.generate_pre_claim_caption()

        message = await update.message.reply_photo(
            photo=base64.b64decode(generated_card.image_b64),
            caption=caption,
            reply_markup=None,  # No buttons during countdown
            parse_mode=ParseMode.HTML,
            reply_to_message_id=update.message.message_id,
        )

        # Spawn background task to handle countdown and reveal claim button
        asyncio.create_task(
            process_claim_countdown(
                chat_id=update.effective_chat.id,
                message_id=message.message_id,
                roll_id=roll_id,
            )
        )

        # Save the file_id returned by Telegram for future use
        await save_card_file_id_from_message(message, card_id)

        if not DEBUG_MODE:
            await asyncio.to_thread(roll_service.record_roll, user.user_id, chat_id_str)

        # Log successful roll
        event_service.log(
            EventType.ROLL,
            RollOutcome.SUCCESS,
            user_id=user.user_id,
            chat_id=chat_id_str,
            card_id=card_id,
            rarity=generated_card.rarity,
            modifier=generated_card.modifier,
            source_name=generated_card.base_name,
            source_type=generated_card.source_type,
            source_id=generated_card.source_id,
        )

    except rolling.NoEligibleUserError:
        # Log roll error
        event_service.log(
            EventType.ROLL,
            RollOutcome.ERROR,
            user_id=user.user_id,
            chat_id=chat_id_str,
            error_message="No eligible user with profile",
        )
        await update.message.reply_text(
            "No enrolled players here have set both a display name and profile photo yet. DM me with /profile <display_name> and a picture to join the fun!",
            reply_to_message_id=update.message.message_id,
        )
        return
    except rolling.ImageGenerationError:
        event_service.log(
            EventType.ROLL,
            RollOutcome.ERROR,
            user_id=user.user_id,
            chat_id=chat_id_str,
            error_message="Image generation failed",
        )
        await update.message.reply_text(
            "Sorry, I couldn't generate an image at the moment.",
            reply_to_message_id=update.message.message_id,
        )
        return
    except Exception as e:
        logger.error(f"Error in /roll: {e}")
        event_service.log(
            EventType.ROLL,
            RollOutcome.ERROR,
            user_id=user.user_id,
            chat_id=chat_id_str,
            error_message=str(e),
        )
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


@verify_user_in_chat
@prevent_concurrency("pending_roll_actions", cross_user=True)
async def handle_reroll(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
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
            source="roll",
        )

        # Log the card generation details
        log_card_generation(generated_card, "reroll")

        # Add new card to database
        new_card_chat_id = active_card.chat_id or (query.message.chat_id if query.message else None)
        new_card_id = await asyncio.to_thread(
            card_service.add_card_from_generated,
            generated_card,
            new_card_chat_id,
        )

        # Delete the original card
        await asyncio.to_thread(card_service.delete_card, active_card.id)

        # Update rolled card state to point to the new card
        rolled_card_manager.mark_rerolled(new_card_id, original_card.rarity)

        # Generate pre-claim caption for the new card (no claim button yet)
        caption = rolled_card_manager.generate_pre_claim_caption()

        # Update message with new image and countdown caption (no buttons during countdown)
        message = await query.edit_message_media(
            media=InputMediaPhoto(
                media=base64.b64decode(generated_card.image_b64),
                caption=caption,
                parse_mode=ParseMode.HTML,
            ),
            reply_markup=None,
        )

        # Spawn background task to handle countdown and reveal claim button
        asyncio.create_task(
            process_claim_countdown(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                roll_id=roll_id,
            )
        )

        # Save the file_id returned by Telegram for future use
        await save_card_file_id_from_message(message, new_card_id)

        # If original card was claimed, refund the claim cost based on the card's rarity
        if original_owner_id is not None and original_claim_chat_id is not None:
            refund_amount = get_claim_cost(active_card.rarity)
            await asyncio.to_thread(
                claim_service.increment_claim_balance,
                original_owner_id,
                original_claim_chat_id,
                refund_amount,
            )

        # Log successful reroll
        event_service.log(
            EventType.REROLL,
            RerollOutcome.SUCCESS,
            user_id=user.user_id,
            chat_id=chat_id_for_roll,
            card_id=new_card_id,
            old_card_id=active_card.id,
            old_rarity=original_card.rarity,
            new_rarity=generated_card.rarity,
            modifier=generated_card.modifier,
            source_name=generated_card.base_name,
            source_type=generated_card.source_type,
            source_id=generated_card.source_id,
        )
    except rolling.NoEligibleUserError:
        # Log reroll error
        chat_id_for_log = active_card.chat_id or (
            str(query.message.chat_id) if query.message else "unknown"
        )
        event_service.log(
            EventType.REROLL,
            RerollOutcome.ERROR,
            user_id=user.user_id,
            chat_id=chat_id_for_log,
            card_id=active_card.id,
            error_message="No eligible user with profile",
        )
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
        # Log reroll error
        chat_id_for_log = active_card.chat_id or (
            str(query.message.chat_id) if query.message else "unknown"
        )
        event_service.log(
            EventType.REROLL,
            RerollOutcome.ERROR,
            user_id=user.user_id,
            chat_id=chat_id_for_log,
            card_id=active_card.id,
            error_message="Image generation failed",
        )
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
