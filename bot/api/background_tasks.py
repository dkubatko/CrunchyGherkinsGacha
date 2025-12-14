"""
Background task functions for async processing.

This module contains all background tasks that are spawned to process
operations asynchronously after responding to the client.
"""

import asyncio
import base64
import logging
from typing import Optional

from telegram.constants import ParseMode

from api.config import (
    create_bot_instance,
    DEBUG_MODE,
    TELEGRAM_TOKEN,
    MAX_SLOT_VICTORY_IMAGE_RETRIES,
    gemini_util,
)
from api.helpers import build_single_card_url
from settings.constants import (
    BURN_RESULT_MESSAGE,
    MINESWEEPER_BET_MESSAGE,
    MINESWEEPER_LOSS_MESSAGE,
    MINESWEEPER_VICTORY_FAILURE_MESSAGE,
    MINESWEEPER_VICTORY_PENDING_MESSAGE,
    MINESWEEPER_VICTORY_RESULT_MESSAGE,
    SLOTS_VICTORY_FAILURE_MESSAGE,
    SLOTS_VICTORY_PENDING_MESSAGE,
    SLOTS_VICTORY_REFUND_MESSAGE,
    SLOTS_VICTORY_RESULT_MESSAGE,
    SLOTS_VIEW_IN_APP_LABEL,
    get_spin_reward,
)
from utils import rolling
from utils.services import card_service, spin_service, thread_service

logger = logging.getLogger(__name__)


async def process_slots_victory_background(
    bot_token: str,
    debug_mode: bool,
    username: str,
    normalized_rarity: str,
    display_name: str,
    chat_id: str,
    source_type: str,
    source_id: int,
    user_id: int,
    gemini_util_instance,
):
    """Process slots victory in background after responding to client."""
    spin_refund_amount = get_spin_reward(normalized_rarity)

    bot = None
    thread_id: Optional[int] = None
    refund_processed = False
    card_generated_and_assigned = False

    try:
        # Initialize bot
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        bot = create_bot_instance()

        # Send pending message
        pending_caption = SLOTS_VICTORY_PENDING_MESSAGE.format(
            username=username,
            rarity=normalized_rarity,
            display_name=display_name,
        )

        # Get thread_id if available
        thread_id = await asyncio.to_thread(thread_service.get_thread_id, chat_id)

        send_params = {
            "chat_id": chat_id,
            "text": pending_caption,
            "parse_mode": ParseMode.HTML,
        }
        if thread_id is not None:
            send_params["message_thread_id"] = thread_id

        pending_message = await bot.send_message(**send_params)

        try:
            # Generate card from source with built-in retry support
            generated_card = await asyncio.to_thread(
                rolling.generate_card_from_source,
                source_type,
                source_id,
                gemini_util_instance,
                normalized_rarity,
                max_retries=MAX_SLOT_VICTORY_IMAGE_RETRIES,
                chat_id=chat_id,
            )

            # Add card to database and assign to winner
            card_id = await asyncio.to_thread(
                card_service.add_card_from_generated,
                generated_card,
                chat_id,
            )

            await asyncio.to_thread(card_service.set_card_owner, card_id, username, user_id)

            # Mark that card was successfully generated and assigned
            card_generated_and_assigned = True

            # Create final caption and keyboard
            final_caption = SLOTS_VICTORY_RESULT_MESSAGE.format(
                username=username,
                rarity=normalized_rarity,
                display_name=display_name,
                card_id=card_id,
                modifier=generated_card.modifier,
                base_name=generated_card.base_name,
            )

            card_url = build_single_card_url(card_id)
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton(SLOTS_VIEW_IN_APP_LABEL, url=card_url)]]
            )

            # Send the card image as a new message and delete the pending message
            card_image = base64.b64decode(generated_card.image_b64)

            photo_params = {
                "chat_id": chat_id,
                "photo": card_image,
                "caption": final_caption,
                "reply_markup": keyboard,
                "parse_mode": ParseMode.HTML,
            }
            if thread_id is not None:
                photo_params["message_thread_id"] = thread_id

            card_message = await bot.send_photo(**photo_params)

            # Delete the pending message
            await bot.delete_message(chat_id=chat_id, message_id=pending_message.message_id)

            # Save the file_id from the card message
            if card_message.photo:
                file_id = card_message.photo[-1].file_id
                await asyncio.to_thread(card_service.update_card_file_id, card_id, file_id)

            logger.info(
                "Successfully processed slots victory for user %s: card %s", username, card_id
            )

        except Exception as exc:
            logger.error("Error processing slots victory for user %s: %s", username, exc)
            # Update pending message with failure
            failure_caption = SLOTS_VICTORY_FAILURE_MESSAGE.format(
                username=username,
                rarity=normalized_rarity,
                display_name=display_name,
            )
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=pending_message.message_id,
                    text=failure_caption,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as edit_exc:
                logger.error("Failed to update failure message: %s", edit_exc)

            # Only refund if card was not generated and assigned
            if spin_refund_amount > 0 and not card_generated_and_assigned:
                refund_processed = await refund_slots_victory_failure(
                    bot=bot,
                    bot_token=TELEGRAM_TOKEN,
                    debug_mode=DEBUG_MODE,
                    username=username,
                    rarity=normalized_rarity,
                    display_name=display_name,
                    chat_id=chat_id,
                    user_id=user_id,
                    spin_amount=spin_refund_amount,
                    thread_id=thread_id,
                )

    except Exception as exc:
        logger.error("Critical error in slots victory background processing: %s", exc)
        # Only refund if card was not generated and assigned
        if spin_refund_amount > 0 and not refund_processed and not card_generated_and_assigned:
            await refund_slots_victory_failure(
                bot=bot,
                bot_token=TELEGRAM_TOKEN,
                debug_mode=DEBUG_MODE,
                username=username,
                rarity=normalized_rarity,
                display_name=display_name,
                chat_id=chat_id,
                user_id=user_id,
                spin_amount=spin_refund_amount,
                thread_id=thread_id,
            )


async def process_burn_notification(
    bot_token: str,
    debug_mode: bool,
    username: str,
    card_rarity: str,
    card_display_name: str,
    spin_amount: int,
    chat_id: str,
):
    """Send burn notification to chat in background after responding to client."""
    try:
        # Initialize bot
        bot = create_bot_instance()

        # Format the burn result message
        burn_message = BURN_RESULT_MESSAGE.format(
            username=username,
            rarity=card_rarity,
            display_name=card_display_name,
            spin_amount=spin_amount,
        )

        # Get thread_id if available
        thread_id = await asyncio.to_thread(thread_service.get_thread_id, chat_id)

        send_params = {
            "chat_id": chat_id,
            "text": burn_message,
            "parse_mode": ParseMode.HTML,
        }
        if thread_id is not None:
            send_params["message_thread_id"] = thread_id

        await bot.send_message(**send_params)

        logger.info("Sent burn notification for user %s in chat %s", username, chat_id)

    except Exception as exc:
        logger.error(
            "Failed to send burn notification for user %s in chat %s: %s",
            username,
            chat_id,
            exc,
        )


async def process_minesweeper_bet_notification(
    username: str,
    card_title: str,
    chat_id: str,
):
    """Send minesweeper bet notification to chat in background after responding to client."""
    try:
        # Initialize bot
        bot = create_bot_instance()

        # Format the bet message
        bet_message = MINESWEEPER_BET_MESSAGE.format(
            username=username,
            card_title=card_title,
        )

        # Get thread_id if available
        thread_id = await asyncio.to_thread(thread_service.get_thread_id, chat_id)

        send_params = {
            "chat_id": chat_id,
            "text": bet_message,
            "parse_mode": ParseMode.HTML,
        }
        if thread_id is not None:
            send_params["message_thread_id"] = thread_id

        await bot.send_message(**send_params)

        logger.info("Sent minesweeper bet notification for user %s in chat %s", username, chat_id)

    except Exception as exc:
        logger.error(
            "Failed to send minesweeper bet notification for user %s in chat %s: %s",
            username,
            chat_id,
            exc,
        )


async def process_minesweeper_victory_background(
    username: str,
    user_id: int,
    chat_id: str,
    rarity: str,
    source_type: str,
    source_id: int,
    display_name: str,
    gemini_util_instance,
):
    """Process minesweeper victory in background after responding to client."""
    bot = None
    thread_id: Optional[int] = None

    try:
        # Initialize bot
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        bot = create_bot_instance()

        # Send pending message
        pending_caption = MINESWEEPER_VICTORY_PENDING_MESSAGE.format(
            username=username,
            rarity=rarity,
            display_name=display_name,
        )

        # Get thread_id if available
        thread_id = await asyncio.to_thread(thread_service.get_thread_id, chat_id)

        send_params = {
            "chat_id": chat_id,
            "text": pending_caption,
            "parse_mode": ParseMode.HTML,
        }
        if thread_id is not None:
            send_params["message_thread_id"] = thread_id

        pending_message = await bot.send_message(**send_params)

        try:
            # Generate card from source with built-in retry support
            generated_card = await asyncio.to_thread(
                rolling.generate_card_from_source,
                source_type,
                source_id,
                gemini_util_instance,
                rarity,
                max_retries=MAX_SLOT_VICTORY_IMAGE_RETRIES,
                chat_id=chat_id,
            )

            # Add card to database and assign to winner
            card_id = await asyncio.to_thread(
                card_service.add_card_from_generated,
                generated_card,
                chat_id,
            )

            await asyncio.to_thread(card_service.set_card_owner, card_id, username, user_id)

            # Create final caption and keyboard
            final_caption = MINESWEEPER_VICTORY_RESULT_MESSAGE.format(
                username=username,
                rarity=rarity,
                display_name=display_name,
                card_id=card_id,
                modifier=generated_card.modifier,
                base_name=generated_card.base_name,
            )

            card_url = build_single_card_url(card_id)
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton(SLOTS_VIEW_IN_APP_LABEL, url=card_url)]]
            )

            # Send the card image as a new message and delete the pending message
            card_image = base64.b64decode(generated_card.image_b64)

            photo_params = {
                "chat_id": chat_id,
                "photo": card_image,
                "caption": final_caption,
                "reply_markup": keyboard,
                "parse_mode": ParseMode.HTML,
            }
            if thread_id is not None:
                photo_params["message_thread_id"] = thread_id

            card_message = await bot.send_photo(**photo_params)

            # Delete the pending message
            await bot.delete_message(chat_id=chat_id, message_id=pending_message.message_id)

            # Save the file_id from the card message
            if card_message.photo:
                file_id = card_message.photo[-1].file_id
                await asyncio.to_thread(card_service.update_card_file_id, card_id, file_id)

            logger.info(
                "Successfully processed minesweeper victory for user %s: card %s", username, card_id
            )

        except Exception as exc:
            logger.error("Error processing minesweeper victory for user %s: %s", username, exc)
            # Update pending message with failure
            failure_caption = MINESWEEPER_VICTORY_FAILURE_MESSAGE.format(
                username=username,
                rarity=rarity,
                display_name=display_name,
            )
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=pending_message.message_id,
                    text=failure_caption,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as edit_exc:
                logger.error("Failed to update failure message: %s", edit_exc)

    except Exception as exc:
        logger.error("Critical error in minesweeper victory background processing: %s", exc)


async def process_minesweeper_loss_background(
    username: str,
    chat_id: str,
    bet_card_id: int,
    card_title: str,
):
    """Process minesweeper loss in background after responding to client."""
    try:
        # Delete the bet card from database
        success = await asyncio.to_thread(card_service.delete_card, bet_card_id)

        if not success:
            logger.error("Failed to delete bet card %s after minesweeper loss", bet_card_id)
            return

        # Initialize bot
        bot = create_bot_instance()

        # Format the loss message
        loss_message = MINESWEEPER_LOSS_MESSAGE.format(
            username=username,
            card_title=card_title,
        )

        # Get thread_id if available
        thread_id = await asyncio.to_thread(thread_service.get_thread_id, chat_id)

        send_params = {
            "chat_id": chat_id,
            "text": loss_message,
            "parse_mode": ParseMode.HTML,
        }
        if thread_id is not None:
            send_params["message_thread_id"] = thread_id

        await bot.send_message(**send_params)

        logger.info(
            "Sent minesweeper loss notification for user %s in chat %s (card %s destroyed)",
            username,
            chat_id,
            bet_card_id,
        )

    except Exception as exc:
        logger.error(
            "Failed to process minesweeper loss for user %s in chat %s: %s",
            username,
            chat_id,
            exc,
        )


async def refund_slots_victory_failure(
    bot,
    bot_token: str,
    debug_mode: bool,
    username: str,
    rarity: str,
    display_name: str,
    chat_id: str,
    user_id: int,
    spin_amount: int,
    thread_id: Optional[int] = None,
) -> bool:
    """Refund spins to the user and notify the chat about the failure."""
    if spin_amount <= 0:
        return False

    try:
        new_total = await asyncio.to_thread(
            spin_service.increment_user_spins, user_id, chat_id, spin_amount
        )
    except Exception as exc:
        logger.error(
            "Failed to refund spins after slot victory failure for user %s in chat %s: %s",
            username,
            chat_id,
            exc,
        )
        return False

    if new_total is None:
        logger.error(
            "Spin refund returned None for user %s in chat %s after slot victory failure",
            username,
            chat_id,
        )
        return False

    if bot is None:
        bot = create_bot_instance()

    message = SLOTS_VICTORY_REFUND_MESSAGE.format(
        username=username,
        rarity=rarity,
        display_name=display_name,
        spin_amount=spin_amount,
    )

    try:
        if thread_id is None:
            thread_id = await asyncio.to_thread(thread_service.get_thread_id, chat_id)

        send_params = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": ParseMode.HTML,
        }
        if thread_id is not None:
            send_params["message_thread_id"] = thread_id

        await bot.send_message(**send_params)
    except Exception as exc:
        logger.error(
            "Failed to send slot victory refund notification for user %s in chat %s: %s",
            username,
            chat_id,
            exc,
        )

    return True
