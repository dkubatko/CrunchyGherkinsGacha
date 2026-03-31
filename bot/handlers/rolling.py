"""
Rolling-related command handlers.

This module contains handlers for rolling new cards/aspects, rerolling,
claiming, and locking rolled items.
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
    save_aspect_file_id_from_message,
)
from settings.constants import (
    REACTION_IN_PROGRESS,
    get_claim_cost,
)
from utils import rolling
from repos import card_repo
from repos import claim_repo
from repos import rolled_card_repo
from repos import rolled_aspect_repo
from repos import roll_repo
from managers import event_manager
from managers import roll_manager
from utils.schemas import User
from utils.decorators import verify_user_in_chat, prevent_concurrency
from utils.roll_manager import RollManager, ClaimStatus
from utils.events import EventType, RollOutcome, RerollOutcome, ClaimOutcome, RollLockOutcome
from api.background_tasks import process_claim_countdown

logger = logging.getLogger(__name__)


@verify_user_in_chat
async def roll(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Roll a new card or aspect."""
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
            if not await asyncio.to_thread(roll_manager.can_roll, user.user_id, chat_id_str):
                hours, minutes = get_time_until_next_roll(user.user_id, chat_id_str)
                await update.message.reply_text(
                    f"You have already rolled. Next roll in {hours} hours {minutes} minutes.",
                    reply_to_message_id=update.message.message_id,
                )
                if not DEBUG_MODE:
                    await context.bot.set_message_reaction(
                        chat_id=update.effective_chat.id,
                        message_id=update.message.message_id,
                        reaction=[],
                    )
                return

        # --- Determine roll type and generate ---
        # If the user has no cards yet, guarantee a base card of themselves
        user_card_count = await asyncio.to_thread(
            card_repo.get_user_card_count, user.user_id, chat_id_str
        )
        first_roll = user_card_count == 0

        roll_result = await asyncio.to_thread(
            rolling.generate_roll_for_chat,
            chat_id_str,
            gemini_util,
            max_retries=MAX_BOT_IMAGE_RETRIES,
            source="roll",
            roll_type="base_card" if first_roll else None,
            profile_type="user" if first_roll else None,
            profile_id=user.user_id if first_roll else None,
        )

        if roll_result.roll_type == "base_card" and roll_result.card is not None:
            await _handle_card_roll(update, context, user, chat_id_str, roll_result.card)
        elif roll_result.roll_type == "aspect" and roll_result.aspect is not None:
            await _handle_aspect_roll(update, context, user, chat_id_str, roll_result.aspect)
        else:
            raise rolling.ImageGenerationError("Roll produced no output")

    except rolling.NoEligibleUserError:
        event_manager.log(
            EventType.ROLL,
            RollOutcome.ERROR,
            user_id=user.user_id,
            chat_id=chat_id_str,
            error_message="No eligible user with profile",
        )
        await update.message.reply_text(
            "No enrolled players here have set both a display name and profile photo yet. "
            "DM me with /profile <display_name> and a picture to join the fun!",
            reply_to_message_id=update.message.message_id,
        )
        return
    except rolling.ImageGenerationError:
        event_manager.log(
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
        event_manager.log(
            EventType.ROLL,
            RollOutcome.ERROR,
            user_id=user.user_id,
            chat_id=chat_id_str,
            error_message=str(e),
        )
        await update.message.reply_text(
            "An error occurred while rolling.",
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


# ---------------------------------------------------------------------------
# Roll sub-handlers (called from roll())
# ---------------------------------------------------------------------------


async def _handle_card_roll(update, context, user, chat_id_str, generated_card):
    """Process a base-card roll."""
    log_card_generation(generated_card, "roll (base card)")

    card_id = await asyncio.to_thread(
        card_repo.add_card_from_generated,
        generated_card,
        update.effective_chat.id,
    )

    # Award claim points to the roller
    claim_reward = get_claim_cost(generated_card.rarity)
    await asyncio.to_thread(
        claim_repo.increment_claim_balance,
        user.user_id,
        chat_id_str,
        claim_reward,
    )

    # Create rolled card entry
    roll_id = await asyncio.to_thread(rolled_card_repo.create_rolled_card, card_id, user.user_id)

    # Generate pre-claim caption via RollManager
    manager = RollManager("card", roll_id)
    caption = manager.generate_pre_claim_caption()

    message = await update.message.reply_photo(
        photo=base64.b64decode(generated_card.image_b64),
        caption=caption,
        reply_markup=None,
        parse_mode=ParseMode.HTML,
        reply_to_message_id=update.message.message_id,
    )

    # Spawn countdown background task
    asyncio.create_task(
        process_claim_countdown(
            chat_id=update.effective_chat.id,
            message_id=message.message_id,
            roll_id=roll_id,
            roll_type="card",
        )
    )

    await save_card_file_id_from_message(message, card_id)

    if not DEBUG_MODE:
        await asyncio.to_thread(roll_repo.record_roll, user.user_id, chat_id_str)

    event_manager.log(
        EventType.ROLL,
        RollOutcome.SUCCESS,
        user_id=user.user_id,
        chat_id=chat_id_str,
        card_id=card_id,
        rarity=generated_card.rarity,
        type="base_card",
        modifier=generated_card.modifier,
        source_name=generated_card.base_name,
        source_type=generated_card.source_type,
        source_id=generated_card.source_id,
    )


async def _handle_aspect_roll(update, context, user, chat_id_str, generated_aspect):
    """Process an aspect roll."""
    logger.info(
        "Aspect roll: '%s' (id=%s, rarity=%s, set='%s') for chat %s",
        generated_aspect.aspect_name,
        generated_aspect.aspect_id,
        generated_aspect.rarity,
        generated_aspect.set_name,
        chat_id_str,
    )

    # Award claim points to the roller
    claim_reward = get_claim_cost(generated_aspect.rarity)
    await asyncio.to_thread(
        claim_repo.increment_claim_balance,
        user.user_id,
        chat_id_str,
        claim_reward,
    )

    # Create rolled aspect entry
    roll_id = await asyncio.to_thread(
        rolled_aspect_repo.create_rolled_aspect,
        generated_aspect.aspect_id,
        user.user_id,
    )

    # Generate pre-claim caption via RollManager
    manager = RollManager("aspect", roll_id)
    caption = manager.generate_pre_claim_caption()

    message = await update.message.reply_photo(
        photo=base64.b64decode(generated_aspect.image_b64),
        caption=caption,
        reply_markup=None,
        parse_mode=ParseMode.HTML,
        reply_to_message_id=update.message.message_id,
    )

    # Spawn countdown background task
    asyncio.create_task(
        process_claim_countdown(
            chat_id=update.effective_chat.id,
            message_id=message.message_id,
            roll_id=roll_id,
            roll_type="aspect",
        )
    )

    await save_aspect_file_id_from_message(message, generated_aspect.aspect_id)

    if not DEBUG_MODE:
        await asyncio.to_thread(roll_repo.record_roll, user.user_id, chat_id_str)

    event_manager.log(
        EventType.ROLL,
        RollOutcome.SUCCESS,
        user_id=user.user_id,
        chat_id=chat_id_str,
        aspect_id=generated_aspect.aspect_id,
        rarity=generated_aspect.rarity,
        type="aspect",
        aspect_name=generated_aspect.aspect_name,
        aspect_definition_id=generated_aspect.aspect_definition_id,
        set_name=generated_aspect.set_name,
    )


# ---------------------------------------------------------------------------
# Callback helpers
# ---------------------------------------------------------------------------


def _parse_roll_callback(data: str) -> tuple:
    """Extract ``(roll_type, roll_id)`` from callback data.

    ``claim_42``  → ``("card", 42)``
    ``aclaim_42`` → ``("aspect", 42)``
    """
    prefix, roll_id_str = data.split("_", 1)
    roll_type = "aspect" if prefix.startswith("a") else "card"
    return roll_type, int(roll_id_str)


def _resolve_chat_id(item_chat_id, query):
    """Resolve a chat-ID string from an item field or Telegram query."""
    if item_chat_id is not None:
        return str(item_chat_id)
    if query.message:
        return str(query.message.chat_id)
    return None


# ---------------------------------------------------------------------------
# Callback handlers  (claim / lock / reroll — unified for card & aspect)
# ---------------------------------------------------------------------------


@verify_user_in_chat
@prevent_concurrency("pending_roll_actions")
async def handle_claim(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle claim button click for both cards and aspects."""
    query = update.callback_query
    roll_type, roll_id = _parse_roll_callback(query.data)
    chat_id = str(update.effective_chat.id) if update.effective_chat else None

    manager = RollManager(roll_type, roll_id)

    item = manager.item
    if item is None:
        await query.answer("Item not found!", show_alert=True)
        return

    if manager.is_being_rerolled():
        await query.answer("Being rerolled, please wait.", show_alert=True)
        return

    claim_result = await asyncio.to_thread(
        manager.claim_item,
        user.username,
        user.user_id,
        chat_id,
    )

    cost_to_spend = claim_result.cost if claim_result.cost is not None else 1
    item_label = roll_type.replace("_", " ").capitalize()

    if claim_result.status is ClaimStatus.INSUFFICIENT_BALANCE:
        message = f"Not enough claim points!\n\nCost: {cost_to_spend}"
        if claim_result.balance is not None:
            message += f"\n\nBalance: {claim_result.balance}"
        await query.answer(message, show_alert=True)
        event_manager.log(
            EventType.CLAIM,
            ClaimOutcome.INSUFFICIENT,
            user_id=user.user_id,
            chat_id=chat_id,
            card_id=item.id if roll_type == "card" else None,
            aspect_id=item.id if roll_type == "aspect" else None,
            type=roll_type,
            cost=cost_to_spend,
            balance=claim_result.balance,
        )
        return

    # Refresh item after claim
    item = manager.item
    item_title = item.title()
    spent_line = f"Spent: {cost_to_spend} claim point{'s' if cost_to_spend != 1 else ''}"

    def _build_claim_message(balance):
        msg = f"{item_label} {item_title} claimed!\n\n{spent_line}"
        if balance is not None:
            msg += f"\n\nRemaining balance: {balance}."
        return msg

    if claim_result.status is ClaimStatus.SUCCESS:
        await query.answer(_build_claim_message(claim_result.balance), show_alert=True)
        event_manager.log(
            EventType.CLAIM,
            ClaimOutcome.SUCCESS,
            user_id=user.user_id,
            chat_id=chat_id,
            card_id=item.id if roll_type == "card" else None,
            aspect_id=item.id if roll_type == "aspect" else None,
            type=roll_type,
            cost=cost_to_spend,
            rarity=item.rarity,
            balance=claim_result.balance,
        )
    elif claim_result.status is ClaimStatus.ALREADY_OWNED_BY_USER:
        remaining_balance = claim_result.balance
        if remaining_balance is None and chat_id and user.user_id:
            remaining_balance = await asyncio.to_thread(
                claim_repo.get_claim_balance, user.user_id, chat_id
            )
        await query.answer(_build_claim_message(remaining_balance), show_alert=True)
        event_manager.log(
            EventType.CLAIM,
            ClaimOutcome.ALREADY_OWNED,
            user_id=user.user_id,
            chat_id=chat_id,
            card_id=item.id if roll_type == "card" else None,
            aspect_id=item.id if roll_type == "aspect" else None,
            type=roll_type,
        )
    else:
        fresh_item = manager.item
        owner = fresh_item.owner if fresh_item else "someone"
        await query.answer(f"Too late! Already claimed by @{owner}.", show_alert=True)
        event_manager.log(
            EventType.CLAIM,
            ClaimOutcome.TAKEN,
            user_id=user.user_id,
            chat_id=chat_id,
            card_id=item.id if roll_type == "card" else None,
            aspect_id=item.id if roll_type == "aspect" else None,
            type=roll_type,
            claimed_by=owner,
        )

    try:
        await query.edit_message_caption(
            caption=manager.generate_caption(),
            reply_markup=manager.generate_keyboard(),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


@verify_user_in_chat
@prevent_concurrency("pending_roll_actions", cross_user=True)
async def handle_lock(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle lock button click for both cards and aspects."""
    query = update.callback_query
    roll_type, roll_id = _parse_roll_callback(query.data)
    chat_id = str(update.effective_chat.id) if update.effective_chat else None

    manager = RollManager(roll_type, roll_id)

    if not manager.is_valid():
        await query.answer("Item not found!", show_alert=True)
        return

    if not manager.is_claimed():
        await query.answer("Must be claimed before it can be locked!", show_alert=True)
        return

    item = manager.item
    if item is None:
        await query.answer("Item not found!", show_alert=True)
        return

    if not manager.can_user_lock(user.user_id, user.username):
        await query.answer("Only the owner can lock!", show_alert=True)
        return

    try:
        lock_result = await asyncio.to_thread(
            manager.lock_item,
            user.user_id,
            chat_id,
        )
    except ValueError as exc:
        logger.error("Lock failed: %s", exc)
        await query.answer("Unable to lock right now.", show_alert=True)
        return

    if not lock_result.success:
        message = f"Not enough claim points!\n\nCost: {lock_result.cost}"
        if lock_result.current_balance is not None:
            message += f"\n\nBalance: {lock_result.current_balance}"
        await query.answer(message, show_alert=True)
        event_manager.log(
            EventType.ROLL_LOCK,
            RollLockOutcome.INSUFFICIENT,
            user_id=user.user_id,
            chat_id=chat_id,
            card_id=item.id if roll_type == "card" else None,
            aspect_id=item.id if roll_type == "aspect" else None,
            type=roll_type,
            cost=lock_result.cost,
            balance=lock_result.current_balance,
        )
        return

    lock_message = "Locked!"
    if lock_result.cost > 0:
        lock_message = (
            "Locked!\n\n"
            f"Spent: {lock_result.cost} claim point{'s' if lock_result.cost != 1 else ''}"
        )
        if lock_result.remaining_balance is not None:
            lock_message += f"\n\nBalance: {lock_result.remaining_balance}"
    await query.answer(lock_message, show_alert=True)

    event_manager.log(
        EventType.ROLL_LOCK,
        RollLockOutcome.LOCKED,
        user_id=user.user_id,
        chat_id=chat_id,
        card_id=item.id if roll_type == "card" else None,
        aspect_id=item.id if roll_type == "aspect" else None,
        type=roll_type,
        cost=lock_result.cost,
        balance=lock_result.remaining_balance,
    )

    try:
        await query.edit_message_caption(
            caption=manager.generate_caption(),
            reply_markup=None,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


@verify_user_in_chat
@prevent_concurrency("pending_roll_actions", cross_user=True)
async def handle_reroll(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle reroll button click for both cards and aspects."""
    query = update.callback_query
    roll_type, roll_id = _parse_roll_callback(query.data)

    manager = RollManager(roll_type, roll_id)

    if not manager.is_valid():
        await query.answer("Item not found!", show_alert=True)
        return

    active_item = manager.item
    if active_item is None:
        await query.answer("Item data unavailable", show_alert=True)
        return

    if not manager.can_user_reroll(user.user_id):
        rolled = manager.rolled
        if rolled and rolled.original_roller_id != user.user_id:
            await query.answer("Only the original roller can reroll!", show_alert=True)
        elif manager.is_reroll_expired():
            await query.answer("Reroll has expired", show_alert=True)
            await query.edit_message_caption(
                caption=manager.generate_caption(),
                reply_markup=manager.generate_keyboard(),
                parse_mode=ParseMode.HTML,
            )
        else:
            await query.answer("Cannot reroll this item", show_alert=True)
        return

    original_item = manager.original_item or active_item
    original_owner_id = active_item.user_id
    original_claim_chat_id = _resolve_chat_id(active_item.chat_id, query)

    try:
        manager.set_being_rerolled(True)
        await query.edit_message_caption(
            caption=manager.generate_caption(),
            parse_mode=ParseMode.HTML,
        )
        await query.answer("Rerolling...")

        chat_id_for_roll = _resolve_chat_id(active_item.chat_id, query)
        if chat_id_for_roll is None:
            raise ValueError("Unable to resolve chat id for reroll")

        downgraded_rarity = rolling.get_downgraded_rarity(original_item.rarity)

        result = await asyncio.to_thread(
            manager.execute_reroll,
            gemini_util,
            chat_id_for_roll,
            downgraded_rarity,
            original_item.rarity,
            max_retries=MAX_BOT_IMAGE_RETRIES,
            source="roll",
        )

        message = await query.edit_message_media(
            media=InputMediaPhoto(
                media=base64.b64decode(result.image_b64),
                caption=manager.generate_pre_claim_caption(),
                parse_mode=ParseMode.HTML,
            ),
            reply_markup=None,
        )

        asyncio.create_task(
            process_claim_countdown(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                roll_id=roll_id,
                roll_type=roll_type,
            )
        )

        if roll_type == "card":
            await save_card_file_id_from_message(message, result.new_item_id)
        else:
            await save_aspect_file_id_from_message(message, result.new_item_id)

        # Refund if the original was claimed
        if original_owner_id is not None and original_claim_chat_id is not None:
            refund_amount = get_claim_cost(active_item.rarity)
            await asyncio.to_thread(
                claim_repo.increment_claim_balance,
                original_owner_id,
                original_claim_chat_id,
                refund_amount,
            )

        event_manager.log(
            EventType.REROLL,
            RerollOutcome.SUCCESS,
            user_id=user.user_id,
            chat_id=chat_id_for_roll,
            old_rarity=result.old_rarity,
            new_rarity=result.rarity,
            **result.event_kwargs,
        )
    except rolling.NoEligibleUserError:
        chat_id_for_log = _resolve_chat_id(active_item.chat_id, query) or "unknown"
        event_manager.log(
            EventType.REROLL,
            RerollOutcome.ERROR,
            user_id=user.user_id,
            chat_id=chat_id_for_log,
            error_message="No eligible user with profile",
        )
        manager.set_being_rerolled(False)
        await query.edit_message_caption(
            caption=manager.generate_caption(),
            reply_markup=manager.generate_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        await query.answer(
            "No enrolled players have set a display name and profile photo yet.",
            show_alert=True,
        )
    except rolling.ImageGenerationError:
        chat_id_for_log = _resolve_chat_id(active_item.chat_id, query) or "unknown"
        event_manager.log(
            EventType.REROLL,
            RerollOutcome.ERROR,
            user_id=user.user_id,
            chat_id=chat_id_for_log,
            error_message="Image generation failed",
        )
        manager.set_being_rerolled(False)
        await query.edit_message_caption(
            caption=manager.generate_caption(),
            reply_markup=manager.generate_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        await query.answer("Sorry, couldn't generate a new image!", show_alert=True)
    except Exception as e:
        logger.error("Error in reroll (roll_type=%s): %s", roll_type, e)
        try:
            manager.set_being_rerolled(False)
            await query.edit_message_caption(
                caption=manager.generate_caption(),
                reply_markup=manager.generate_keyboard(),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        try:
            await query.answer("An error occurred during reroll!", show_alert=True)
        except Exception as cb_err:
            logger.warning("Failed to answer callback query: %s", cb_err)
