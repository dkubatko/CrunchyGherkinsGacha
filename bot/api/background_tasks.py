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
    NO_GENERATION,
    TELEGRAM_TOKEN,
    MAX_SLOT_VICTORY_IMAGE_RETRIES,
    gemini_util,
)
from api.helpers import build_single_card_url
from settings.constants import (
    BURN_RESULT_MESSAGE,
    CARD_STATUS_PRE_CLAIM_MESSAGES,
    CLAIM_UNLOCK_DELAY_HIGH,
    CLAIM_UNLOCK_DELAY_LOW,
    PRE_CLAIM_ROTATION_INTERVAL,
    MEGASPIN_VICTORY_FAILURE_MESSAGE,
    MEGASPIN_VICTORY_PENDING_MESSAGE,
    MEGASPIN_VICTORY_RESULT_MESSAGE,
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
from utils.events import EventType, SpinOutcome, MegaspinOutcome, MinesweeperOutcome
from utils.services import card_service, event_service, spin_service, thread_service

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
    is_megaspin: bool = False,
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

        # Send pending message (use megaspin variant if applicable)
        pending_message_template = (
            MEGASPIN_VICTORY_PENDING_MESSAGE if is_megaspin else SLOTS_VICTORY_PENDING_MESSAGE
        )
        pending_caption = pending_message_template.format(
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
            # Skip card generation if NO_GENERATION is enabled (debug mode only)
            if NO_GENERATION:
                logger.info("NO_GENERATION mode: Skipping card generation for slots victory")
                # Edit the pending message to indicate skipped generation
                skip_caption = (
                    f"🎰 <b>SLOTS WIN!</b> (Generation Disabled)\n\n"
                    f"👤 Winner: @{username}\n"
                    f"⭐ Rarity: <b>{normalized_rarity}</b>\n"
                    f"🎭 Source: {display_name}\n\n"
                    f"<i>Card generation is disabled in debug mode.</i>"
                )
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=pending_message.message_id,
                    text=skip_caption,
                    parse_mode=ParseMode.HTML,
                )
                # Give spin refund since user "won"
                await asyncio.to_thread(
                    spin_service.increment_user_spins, user_id, chat_id, spin_refund_amount
                )
                refund_processed = True
                logger.info(
                    "NO_GENERATION: Slots victory skipped for user %s, refunded %d spins",
                    username,
                    spin_refund_amount,
                )
                return

            # Generate card from profile with built-in retry support
            generated_card = await asyncio.to_thread(
                rolling.generate_card_from_profile,
                source_type,
                source_id,
                gemini_util_instance,
                normalized_rarity,
                max_retries=MAX_SLOT_VICTORY_IMAGE_RETRIES,
                chat_id=chat_id,
                source="slots",
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

            # Log spin/megaspin card win event after successful card generation
            if is_megaspin:
                event_service.log(
                    EventType.MEGASPIN,
                    MegaspinOutcome.SUCCESS,
                    user_id=user_id,
                    chat_id=chat_id,
                    card_id=card_id,
                    rarity=normalized_rarity,
                    modifier=generated_card.modifier,
                    source_name=generated_card.base_name,
                    source_type=source_type,
                    source_id=source_id,
                )
            else:
                event_service.log(
                    EventType.SPIN,
                    SpinOutcome.CARD_WIN,
                    user_id=user_id,
                    chat_id=chat_id,
                    card_id=card_id,
                    rarity=normalized_rarity,
                    modifier=generated_card.modifier,
                    source_name=generated_card.base_name,
                    source_type=source_type,
                    source_id=source_id,
                )

            # Create final caption and keyboard (use megaspin variant if applicable)
            result_message_template = (
                MEGASPIN_VICTORY_RESULT_MESSAGE if is_megaspin else SLOTS_VICTORY_RESULT_MESSAGE
            )
            final_caption = result_message_template.format(
                username=username,
                rarity=normalized_rarity,
                display_name=display_name,
                card_id=card_id,
                modifier=generated_card.modifier,
                base_name=generated_card.base_name,
                set_name=(generated_card.set_name or "").title(),
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
            # Update pending message with failure (use megaspin variant if applicable)
            failure_message_template = (
                MEGASPIN_VICTORY_FAILURE_MESSAGE if is_megaspin else SLOTS_VICTORY_FAILURE_MESSAGE
            )
            failure_caption = failure_message_template.format(
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


async def process_rtb_result_notification(
    username: str,
    chat_id: str,
    result: str,  # "won", "lost", or "cashed out"
    amount: int,
    multiplier: float,
):
    """Send RTB game result notification to chat in background after responding to client."""
    from settings.constants import RTB_RESULT_MESSAGE

    try:
        # Initialize bot
        bot = create_bot_instance()

        # Format the message with the action
        message = RTB_RESULT_MESSAGE.format(
            username=username,
            action=result,
            amount=amount,
            multiplier=multiplier,
        )

        # Get thread_id if available
        thread_id = await asyncio.to_thread(thread_service.get_thread_id, chat_id)

        send_params = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": ParseMode.HTML,
        }
        if thread_id is not None:
            send_params["message_thread_id"] = thread_id

        await bot.send_message(**send_params)

        logger.info("Sent RTB %s notification for user %s in chat %s", result, username, chat_id)

    except Exception as exc:
        logger.error(
            "Failed to send RTB result notification for user %s in chat %s: %s",
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
    game_id: int,
    cells_revealed: int,
    claim_points_earned: int,
    bet_card_id: int,
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
            # Generate card from profile with built-in retry support
            generated_card = await asyncio.to_thread(
                rolling.generate_card_from_profile,
                source_type,
                source_id,
                gemini_util_instance,
                rarity,
                max_retries=MAX_SLOT_VICTORY_IMAGE_RETRIES,
                chat_id=chat_id,
                source="slots",
            )

            # Add card to database and assign to winner
            card_id = await asyncio.to_thread(
                card_service.add_card_from_generated,
                generated_card,
                chat_id,
            )

            await asyncio.to_thread(card_service.set_card_owner, card_id, username, user_id)

            # Log minesweeper win event after successful card generation
            event_service.log(
                EventType.MINESWEEPER,
                MinesweeperOutcome.WON,
                user_id=user_id,
                chat_id=chat_id,
                card_id=card_id,
                game_id=game_id,
                cells_revealed=cells_revealed,
                claim_points_earned=claim_points_earned,
                bet_card_id=bet_card_id,
                modifier=generated_card.modifier,
                source_name=generated_card.base_name,
                source_type=source_type,
                source_id=source_id,
                rarity=rarity,
            )

            # Create final caption and keyboard
            final_caption = MINESWEEPER_VICTORY_RESULT_MESSAGE.format(
                username=username,
                rarity=rarity,
                display_name=display_name,
                card_id=card_id,
                modifier=generated_card.modifier,
                base_name=generated_card.base_name,
                set_name=(generated_card.set_name or "").title(),
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


async def send_achievement_notification(
    user_id: int,
    chat_id: str,
    user_achievement,
) -> bool:
    """
    Send a notification when a user unlocks an achievement.

    Args:
        user_id: The user who earned the achievement.
        chat_id: The chat where the triggering event occurred.
        user_achievement: The UserAchievement schema with achievement details.

    Returns:
        True if notification was sent successfully, False otherwise.
    """
    from settings.constants import ACHIEVEMENT_NOTIFICATION_MESSAGE
    from utils.services import user_service

    try:
        bot = create_bot_instance()

        # Get username for mention
        username = await asyncio.to_thread(user_service.get_username_for_user_id, user_id)
        if not username:
            logger.warning("Cannot send achievement notification: no username for user %d", user_id)
            return False

        # Get thread_id if available
        thread_id = await asyncio.to_thread(thread_service.get_thread_id, chat_id)

        # Build notification message
        achievement = user_achievement.achievement
        achievement_name = achievement.name if achievement else "Unknown Achievement"
        achievement_desc = achievement.description if achievement else ""

        message = ACHIEVEMENT_NOTIFICATION_MESSAGE.format(
            username=username,
            achievement_name=achievement_name,
            achievement_desc=achievement_desc,
        )

        send_params = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": ParseMode.HTML,
        }
        if thread_id is not None:
            send_params["message_thread_id"] = thread_id

        await bot.send_message(**send_params)

        logger.info(
            "Sent achievement notification: user=%d earned '%s' in chat=%s",
            user_id,
            achievement_name,
            chat_id,
        )
        return True

    except Exception as exc:
        logger.error(
            "Failed to send achievement notification for user %d in chat %s: %s",
            user_id,
            chat_id,
            exc,
            exc_info=True,
        )
        return False


async def process_claim_countdown(
    chat_id: int,
    message_id: int,
    roll_id: int,
    delay_low: float = CLAIM_UNLOCK_DELAY_LOW,
    delay_high: float = CLAIM_UNLOCK_DELAY_HIGH,
) -> None:
    """
    Process the claim countdown for a newly rolled card.

    Rotates through fun messages during the delay, then reveals the claim button.
    Message rotation is best-effort; the final reveal is retried on failure.

    Args:
        chat_id: The chat where the message was sent.
        message_id: The ID of the message to edit.
        roll_id: The roll ID to use for generating captions/keyboards.
        delay_low: Minimum delay in seconds (default: CLAIM_UNLOCK_DELAY_LOW).
        delay_high: Maximum delay in seconds (default: CLAIM_UNLOCK_DELAY_HIGH).
    """
    import random

    from telegram.error import NetworkError, RetryAfter, TimedOut

    from utils.rolled_card import RolledCardManager

    bot = create_bot_instance()

    def get_manager_if_active() -> Optional[RolledCardManager]:
        """Return RolledCardManager if card is still claimable, else None."""
        manager = RolledCardManager(roll_id)
        if not manager.is_valid() or manager.is_claimed() or manager.is_being_rerolled():
            return None
        return manager

    try:
        # === Phase 1: Rotate messages during delay ===
        total_delay = random.uniform(delay_low, delay_high)
        interval = PRE_CLAIM_ROTATION_INTERVAL

        # Calculate iterations and leftover
        num_iterations = int(total_delay // interval)
        leftover = total_delay - (num_iterations * interval)

        logger.info(
            "Claim countdown started (roll_id=%d): delay=%.2fs, iterations=%d",
            roll_id,
            total_delay,
            num_iterations,
        )

        # Get shuffled messages for rotation
        messages = CARD_STATUS_PRE_CLAIM_MESSAGES.copy()
        random.shuffle(messages)

        for i in range(num_iterations):
            if get_manager_if_active() is None:
                logger.debug("Claim countdown aborted early (roll_id=%d)", roll_id)
                return

            # Best-effort caption update
            try:
                manager = get_manager_if_active()
                if manager is None:
                    return
                message_text = messages[i % len(messages)]
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=manager.generate_pre_claim_caption(message_text),
                    parse_mode=ParseMode.HTML,
                )
            except (RetryAfter, TimedOut, NetworkError, Exception):
                pass  # Best effort, ignore failures

            # Wait for interval, add leftover to final iteration
            sleep_time = interval + leftover if i == num_iterations - 1 else interval
            await asyncio.sleep(sleep_time)

        # Handle case where total_delay < interval (no iterations)
        if num_iterations == 0:
            await asyncio.sleep(total_delay)

        if get_manager_if_active() is None:
            logger.debug("Claim countdown aborted after delay (roll_id=%d)", roll_id)
            return

        # === Phase 2: Reveal claim button (critical, with retries) ===
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries):
            manager = get_manager_if_active()
            if manager is None:
                logger.debug(
                    "Claim countdown final: card no longer claimable (roll_id=%d)", roll_id
                )
                return

            try:
                final_caption = manager.generate_caption()
                final_keyboard = manager.generate_keyboard()

                edited_message = await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=final_caption,
                    reply_markup=final_keyboard,
                    parse_mode=ParseMode.HTML,
                )

                # Verify keyboard was attached (Telegram echoes the edited message back)
                if (
                    final_keyboard is not None
                    and edited_message
                    and getattr(edited_message, "reply_markup", None) is None
                ):
                    raise RuntimeError("Keyboard not attached in response")

                logger.info("Claim button revealed (roll_id=%d)", roll_id)
                return  # Success

            except RetryAfter as e:
                wait_time = e.retry_after
                logger.warning(
                    "Rate limited on reveal (roll_id=%d), attempt %d/%d, waiting %.1fs",
                    roll_id,
                    attempt + 1,
                    max_retries,
                    wait_time,
                )
                await asyncio.sleep(wait_time)

            except (TimedOut, NetworkError, RuntimeError) as e:
                logger.warning(
                    "Reveal failed (roll_id=%d), attempt %d/%d: %s",
                    roll_id,
                    attempt + 1,
                    max_retries,
                    e,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (2**attempt))

            except Exception as e:
                logger.warning(
                    "Unexpected error on reveal (roll_id=%d), attempt %d/%d: %s",
                    roll_id,
                    attempt + 1,
                    max_retries,
                    e,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (2**attempt))

        logger.error(
            "Failed to reveal claim button after %d attempts (roll_id=%d)", max_retries, roll_id
        )

    except Exception as exc:
        logger.error("Fatal error in claim countdown (roll_id=%d): %s", roll_id, exc)
