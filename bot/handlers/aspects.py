"""
Aspect-related command handlers.

This module contains handlers for burning aspects, locking/unlocking aspects,
and recycling aspects into upgraded aspects.
"""

import asyncio
import base64
import html
import logging
import random

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from config import DEBUG_MODE, MAX_BOT_IMAGE_RETRIES, MINIAPP_URL_ENV, gemini_util
from handlers.helpers import build_burning_text
from settings.constants import (
    RECYCLE_ALLOWED_RARITIES,
    RECYCLE_UPGRADE_MAP,
    SLOTS_VIEW_IN_APP_LABEL,
    ASPECT_CAPTION_BASE,
    get_spin_reward,
    get_lock_cost,
    get_recycle_cost,
    # Aspect Burn constants
    ASPECT_BURN_USAGE_MESSAGE,
    ASPECT_BURN_DM_RESTRICTED_MESSAGE,
    ASPECT_BURN_INVALID_ID_MESSAGE,
    ASPECT_BURN_NOT_FOUND_MESSAGE,
    ASPECT_BURN_NOT_YOURS_MESSAGE,
    ASPECT_BURN_CHAT_MISMATCH_MESSAGE,
    ASPECT_BURN_LOCKED_MESSAGE,
    ASPECT_BURN_EQUIPPED_MESSAGE,
    ASPECT_BURN_CONFIRM_MESSAGE,
    ASPECT_BURN_CANCELLED_MESSAGE,
    ASPECT_BURN_ALREADY_RUNNING_MESSAGE,
    ASPECT_BURN_PROCESSING_MESSAGE,
    ASPECT_BURN_FAILURE_MESSAGE,
    ASPECT_BURN_SUCCESS_MESSAGE,
    # Aspect Lock constants
    ASPECT_LOCK_USAGE_MESSAGE,
    ASPECT_LOCK_NOT_FOUND_MESSAGE,
    ASPECT_LOCK_NOT_YOURS_MESSAGE,
    # Aspect Recycle constants
    ASPECT_RECYCLE_USAGE_MESSAGE,
    ASPECT_RECYCLE_DM_RESTRICTED_MESSAGE,
    ASPECT_RECYCLE_SELECT_RARITY_MESSAGE,
    ASPECT_RECYCLE_CONFIRM_MESSAGE,
    ASPECT_RECYCLE_INSUFFICIENT_MESSAGE,
    ASPECT_RECYCLE_ALREADY_RUNNING_MESSAGE,
    ASPECT_RECYCLE_NOT_YOURS_MESSAGE,
    ASPECT_RECYCLE_UNKNOWN_RARITY_MESSAGE,
    ASPECT_RECYCLE_FAILURE_NOT_ENOUGH,
    ASPECT_RECYCLE_FAILURE_IMAGE,
    ASPECT_RECYCLE_FAILURE_UNEXPECTED,
)
from utils import rolling
from utils.miniapp import encode_single_card_token
from utils.services import (
    aspect_service,
    claim_service,
    event_service,
    spin_service,
)
from utils.schemas import User
from utils.decorators import verify_user_in_chat
from utils.events import (
    EventType,
    LockOutcome,
    BurnOutcome,
    RecycleOutcome,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Burn Aspect Handlers
# =============================================================================


@verify_user_in_chat
async def burn(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Burn an aspect for spins."""
    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type == ChatType.PRIVATE and not DEBUG_MODE:
        await message.reply_text(
            ASPECT_BURN_DM_RESTRICTED_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    if not context.args:
        await message.reply_text(
            ASPECT_BURN_USAGE_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    try:
        aspect_id = int(context.args[0])
    except ValueError:
        await message.reply_text(
            ASPECT_BURN_INVALID_ID_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    aspect = await asyncio.to_thread(aspect_service.get_aspect_by_id, aspect_id)
    if not aspect:
        await message.reply_text(
            ASPECT_BURN_NOT_FOUND_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    chat_id_str = str(chat.id)
    if aspect.chat_id != chat_id_str:
        await message.reply_text(
            ASPECT_BURN_CHAT_MISMATCH_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    if aspect.user_id != user.user_id:
        await message.reply_text(
            ASPECT_BURN_NOT_YOURS_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    if aspect.locked:
        await message.reply_text(
            ASPECT_BURN_LOCKED_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    spin_reward = get_spin_reward(aspect.rarity)
    if spin_reward <= 0:
        logger.error("No spin reward configured for rarity %s", aspect.rarity)
        await message.reply_text(
            ASPECT_BURN_FAILURE_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    aspect_name = html.escape(aspect.display_name)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Burn it!", callback_data=f"aburn_yes_{aspect_id}_{user.user_id}"
                ),
                InlineKeyboardButton(
                    "Cancel", callback_data=f"aburn_cancel_{aspect_id}_{user.user_id}"
                ),
            ]
        ]
    )

    await message.reply_text(
        ASPECT_BURN_CONFIRM_MESSAGE.format(
            aspect_id=aspect.id,
            rarity=aspect.rarity,
            aspect_name=aspect_name,
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
    user: User,
) -> None:
    """Handle aspect burn confirmation callback."""
    query = update.callback_query
    if not query:
        return

    data_parts = query.data.split("_")
    if len(data_parts) < 4:
        await query.answer()
        return

    _, action, aspect_id_str, target_user_id_str = data_parts[:4]

    try:
        aspect_id = int(aspect_id_str)
        target_user_id = int(target_user_id_str)
    except ValueError:
        await query.answer(ASPECT_BURN_FAILURE_MESSAGE, show_alert=True)
        return

    if target_user_id != user.user_id:
        await query.answer(ASPECT_BURN_NOT_YOURS_MESSAGE)
        return

    chat = update.effective_chat
    chat_id_str = str(chat.id) if chat else None

    if action == "cancel":
        await query.answer(ASPECT_BURN_CANCELLED_MESSAGE)
        if chat_id_str:
            event_service.log(
                EventType.BURN,
                BurnOutcome.CANCELLED,
                user_id=user.user_id,
                chat_id=chat_id_str,
                aspect_id=aspect_id,
            )
        try:
            await query.message.delete()
        except Exception:
            try:
                await query.edit_message_text(ASPECT_BURN_CANCELLED_MESSAGE)
            except Exception:
                pass
        return

    if action != "yes":
        await query.answer()
        return

    burning_users = context.bot_data.setdefault("burning_users", set())
    if user.user_id in burning_users:
        await query.answer(ASPECT_BURN_ALREADY_RUNNING_MESSAGE, show_alert=True)
        return

    burning_users.add(user.user_id)

    try:
        if not chat_id_str:
            await query.answer(ASPECT_BURN_FAILURE_MESSAGE, show_alert=True)
            return

        # Fetch the aspect to get display info before burning
        aspect = await asyncio.to_thread(aspect_service.get_aspect_by_id, aspect_id)
        if not aspect:
            await query.answer(ASPECT_BURN_NOT_FOUND_MESSAGE, show_alert=True)
            try:
                await query.edit_message_text(ASPECT_BURN_NOT_FOUND_MESSAGE)
            except Exception:
                pass
            return

        if aspect.chat_id != chat_id_str:
            await query.answer(ASPECT_BURN_CHAT_MISMATCH_MESSAGE, show_alert=True)
            try:
                await query.edit_message_text(ASPECT_BURN_CHAT_MISMATCH_MESSAGE)
            except Exception:
                pass
            return

        if aspect.user_id != user.user_id:
            await query.answer(ASPECT_BURN_NOT_YOURS_MESSAGE, show_alert=True)
            try:
                await query.edit_message_text(ASPECT_BURN_NOT_YOURS_MESSAGE)
            except Exception:
                pass
            return

        aspect_name = html.escape(aspect.display_name)
        spin_reward = get_spin_reward(aspect.rarity)

        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        try:
            await query.edit_message_text(ASPECT_BURN_PROCESSING_MESSAGE)
        except Exception:
            pass

        reward = await asyncio.to_thread(
            aspect_service.burn_aspect, aspect_id, user.user_id, chat_id_str
        )

        if reward is None:
            await query.answer(ASPECT_BURN_FAILURE_MESSAGE, show_alert=True)
            try:
                await query.edit_message_text(ASPECT_BURN_FAILURE_MESSAGE)
            except Exception:
                pass
            event_service.log(
                EventType.BURN,
                BurnOutcome.ERROR,
                user_id=user.user_id,
                chat_id=chat_id_str,
                aspect_id=aspect_id,
                error_message="burn_aspect returned None",
            )
            return

        # Get updated spin balance for the success message
        spins_record = await asyncio.to_thread(
            spin_service.get_user_spins, user.user_id, chat_id_str
        )
        new_spin_total = spins_record.count if spins_record else reward

        header = f"<b><s>🔥🔮 [{aspect_id}] {aspect.rarity} {aspect_name}🔥</s></b>"
        success_block = ASPECT_BURN_SUCCESS_MESSAGE.format(
            spin_reward=reward,
            new_spin_total=new_spin_total,
        )

        final_text = f"{header}\n\n{success_block}"

        await query.edit_message_text(
            final_text,
            parse_mode=ParseMode.HTML,
        )
        await query.answer("Burn complete!")

        event_service.log(
            EventType.BURN,
            BurnOutcome.SUCCESS,
            user_id=user.user_id,
            chat_id=chat_id_str,
            aspect_id=aspect_id,
            rarity=aspect.rarity,
            spin_reward=reward,
            new_spin_total=new_spin_total,
        )

        logger.info(
            "User %s burned aspect %s in chat %s for %s spins",
            user.user_id,
            aspect_id,
            chat_id_str,
            reward,
        )
    except Exception as exc:
        logger.exception("Unexpected error during aspect burn for aspect %s: %s", aspect_id, exc)
        event_service.log(
            EventType.BURN,
            BurnOutcome.ERROR,
            user_id=user.user_id,
            chat_id=chat_id_str,
            aspect_id=aspect_id,
            error_message=str(exc),
        )
        await query.answer(ASPECT_BURN_FAILURE_MESSAGE, show_alert=True)
        try:
            await query.edit_message_text(ASPECT_BURN_FAILURE_MESSAGE)
        except Exception:
            pass
    finally:
        burning_users.discard(user.user_id)


# =============================================================================
# Lock Aspect Handlers
# =============================================================================


@verify_user_in_chat
async def lock_aspect_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Initiate lock/unlock for an aspect by ID."""
    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type == ChatType.PRIVATE and not DEBUG_MODE:
        await message.reply_text("Only allowed to lock aspects in the group chat.")
        return

    if len(context.args) != 1:
        await message.reply_text(
            ASPECT_LOCK_USAGE_MESSAGE,
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        aspect_id = int(context.args[0])
    except ValueError:
        await message.reply_text("Aspect ID must be a number.")
        return

    aspect = await asyncio.to_thread(aspect_service.get_aspect_by_id, aspect_id)
    if not aspect:
        await message.reply_text(ASPECT_LOCK_NOT_FOUND_MESSAGE)
        return

    if aspect.user_id != user.user_id:
        await message.reply_text(ASPECT_LOCK_NOT_YOURS_MESSAGE)
        return

    aspect_name = html.escape(aspect.display_name)
    chat_id_str = str(chat.id)
    lock_cost = get_lock_cost(aspect.rarity)

    if aspect.locked:
        prompt_text = f"Unlock <b>🔮 [{aspect.id}] {aspect_name}</b>?"
    else:
        balance = await asyncio.to_thread(
            claim_service.get_claim_balance, user.user_id, chat_id_str
        )
        prompt_text = (
            f"Lock <b>🔮 [{aspect.id}] {aspect_name}</b>?\n\n"
            f"Cost: <b>{lock_cost}</b> claim point{'s' if lock_cost != 1 else ''}\n"
            f"Balance: <b>{balance}</b>"
        )
        if balance < lock_cost:
            await message.reply_text(
                f"Not enough claim points to lock this aspect.\n\n"
                f"Cost: <b>{lock_cost}</b>\nBalance: <b>{balance}</b>",
                parse_mode=ParseMode.HTML,
                reply_to_message_id=message.message_id,
            )
            return

    keyboard = [
        [
            InlineKeyboardButton(
                "Yes", callback_data=f"alockaspect_yes_{aspect_id}_{user.user_id}"
            ),
            InlineKeyboardButton("No", callback_data=f"alockaspect_no_{aspect_id}_{user.user_id}"),
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
async def handle_lock_aspect_confirm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Handle confirmation for locking/unlocking an aspect."""
    query = update.callback_query
    if not query:
        return

    data_parts = query.data.split("_")
    # alockaspect_yes_{aspect_id}_{user_id} → ['alockaspect', 'yes', '{id}', '{uid}']
    if len(data_parts) < 4:
        await query.answer("Invalid request.", show_alert=True)
        return

    _, action, aspect_id_str, target_user_id_str = data_parts[:4]

    try:
        aspect_id = int(aspect_id_str)
        target_user_id = int(target_user_id_str)
    except ValueError:
        await query.answer("Invalid aspect or user ID.", show_alert=True)
        return

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

    chat = update.effective_chat
    if not chat:
        await query.answer("Chat context unavailable.", show_alert=True)
        return

    chat_id_str = str(chat.id)

    # Fetch aspect first to know rarity / current lock state
    aspect = await asyncio.to_thread(aspect_service.get_aspect_by_id, aspect_id)
    if not aspect or aspect.user_id != user.user_id:
        await query.answer("Aspect not found or not owned by you.", show_alert=True)
        try:
            await query.edit_message_text("Aspect not found or not owned by you.")
        except Exception:
            pass
        return

    aspect_name = html.escape(aspect.display_name)
    lock_cost = get_lock_cost(aspect.rarity)

    if not aspect.locked:
        # Locking — charge claim points
        balance = await asyncio.to_thread(
            claim_service.get_claim_balance, user.user_id, chat_id_str
        )
        if balance < lock_cost:
            await query.answer("Not enough claim points.", show_alert=True)
            try:
                await query.edit_message_text(
                    f"Not enough claim points to lock this aspect.\n\n"
                    f"Cost: <b>{lock_cost}</b>\nBalance: <b>{balance}</b>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            return

        remaining = await asyncio.to_thread(
            claim_service.reduce_claim_points, user.user_id, chat_id_str, lock_cost
        )
        if remaining is None:
            await query.answer("Not enough claim points.", show_alert=True)
            return

    new_lock_state = await asyncio.to_thread(aspect_service.lock_aspect, aspect_id, user.user_id)

    if new_lock_state is None:
        await query.answer("Aspect not found or not owned by you.", show_alert=True)
        try:
            await query.edit_message_text("Aspect not found or not owned by you.")
        except Exception:
            pass
        return

    if new_lock_state:
        remaining_balance = await asyncio.to_thread(
            claim_service.get_claim_balance, user.user_id, chat_id_str
        )
        response_text = (
            f"🔒 <b>🔮 [{aspect_id}] {aspect_name}</b> locked!\n\n"
            f"Remaining balance: <b>{remaining_balance}</b>"
        )
        await query.answer(f"{aspect_name} locked!", show_alert=False)
        event_service.log(
            EventType.LOCK,
            LockOutcome.LOCKED,
            user_id=user.user_id,
            chat_id=chat_id_str,
            aspect_id=aspect_id,
            cost=lock_cost,
            via="command",
        )
    else:
        response_text = f"🔓 <b>🔮 [{aspect_id}] {aspect_name}</b> unlocked!"
        await query.answer(f"{aspect_name} unlocked!", show_alert=False)
        event_service.log(
            EventType.LOCK,
            LockOutcome.UNLOCKED,
            user_id=user.user_id,
            chat_id=chat_id_str,
            aspect_id=aspect_id,
            via="command",
        )

    try:
        await query.edit_message_text(response_text, parse_mode=ParseMode.HTML)
    except Exception:
        pass


# =============================================================================
# Recycle Aspect Handlers
# =============================================================================


@verify_user_in_chat
async def recycle(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Recycle aspects of a given rarity for an upgraded aspect."""
    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type == ChatType.PRIVATE and not DEBUG_MODE:
        await message.reply_text(
            ASPECT_RECYCLE_DM_RESTRICTED_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    if not context.args:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Common", callback_data=f"arecycle_select_common_{user.user_id}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "Rare", callback_data=f"arecycle_select_rare_{user.user_id}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "Epic", callback_data=f"arecycle_select_epic_{user.user_id}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "Cancel", callback_data=f"arecycle_cancel_none_{user.user_id}"
                    ),
                ],
            ]
        )
        await message.reply_text(
            ASPECT_RECYCLE_SELECT_RARITY_MESSAGE,
            reply_markup=keyboard,
            reply_to_message_id=message.message_id,
            parse_mode=ParseMode.HTML,
        )
        return

    rarity_key = context.args[0].lower()
    if rarity_key not in RECYCLE_ALLOWED_RARITIES:
        await message.reply_text(
            ASPECT_RECYCLE_UNKNOWN_RARITY_MESSAGE,
            reply_to_message_id=message.message_id,
        )
        return

    rarity_name = RECYCLE_ALLOWED_RARITIES[rarity_key]
    upgrade_rarity = RECYCLE_UPGRADE_MAP[rarity_name]
    required = get_recycle_cost(rarity_name)
    chat_id_str = str(chat.id)

    # Get unequipped aspects for this user/chat, filter by rarity + unlocked
    aspects = await asyncio.to_thread(
        aspect_service.get_user_aspects, user.user_id, chat_id=chat_id_str
    )
    eligible = [a for a in aspects if a.rarity == rarity_name and not a.locked]

    if len(eligible) < required:
        await message.reply_text(
            ASPECT_RECYCLE_INSUFFICIENT_MESSAGE.format(
                required=required,
                rarity=rarity_name.lower(),
            ),
            reply_to_message_id=message.message_id,
        )
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Yes!", callback_data=f"arecycle_yes_{rarity_key}_{user.user_id}"
                ),
                InlineKeyboardButton(
                    "Cancel", callback_data=f"arecycle_cancel_{rarity_key}_{user.user_id}"
                ),
            ]
        ]
    )

    await message.reply_text(
        ASPECT_RECYCLE_CONFIRM_MESSAGE.format(
            burn_count=required,
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
    user: User,
) -> None:
    """Handle aspect recycle confirmation callback."""
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
        await query.answer(ASPECT_RECYCLE_NOT_YOURS_MESSAGE)
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

    rarity_name = RECYCLE_ALLOWED_RARITIES.get(rarity_key)
    if not rarity_name:
        await query.answer(ASPECT_RECYCLE_UNKNOWN_RARITY_MESSAGE, show_alert=True)
        return

    if action == "select":
        # User selected a rarity from the selection menu
        chat = update.effective_chat
        if not chat:
            await query.answer()
            return

        upgrade_rarity = RECYCLE_UPGRADE_MAP[rarity_name]
        required = get_recycle_cost(rarity_name)
        chat_id_str = str(chat.id)

        aspects = await asyncio.to_thread(
            aspect_service.get_user_aspects, user.user_id, chat_id=chat_id_str
        )
        eligible = [a for a in aspects if a.rarity == rarity_name and not a.locked]

        if len(eligible) < required:
            await query.answer(
                f"You need at least {required} unlocked {rarity_name.lower()} aspects to recycle.",
                show_alert=True,
            )
            return

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Yes!", callback_data=f"arecycle_yes_{rarity_key}_{user.user_id}"
                    ),
                    InlineKeyboardButton(
                        "Cancel", callback_data=f"arecycle_cancel_{rarity_key}_{user.user_id}"
                    ),
                ]
            ]
        )

        await query.edit_message_text(
            text=ASPECT_RECYCLE_CONFIRM_MESSAGE.format(
                burn_count=required,
                rarity=rarity_name,
                upgraded_rarity=upgrade_rarity,
            ),
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        await query.answer()
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
        await query.answer(ASPECT_RECYCLE_ALREADY_RUNNING_MESSAGE, show_alert=True)
        return

    recycling_users.add(user.user_id)

    chat_id = query.message.chat_id
    message_id = query.message.message_id
    upgrade_rarity = RECYCLE_UPGRADE_MAP.get(rarity_name)

    if not upgrade_rarity:
        await query.answer("Unable to upgrade this rarity.", show_alert=True)
        recycling_users.discard(user.user_id)
        return

    required = get_recycle_cost(rarity_name)
    chat_id_str = str(chat_id)

    try:
        aspects = await asyncio.to_thread(
            aspect_service.get_user_aspects, user.user_id, chat_id=chat_id_str
        )
        eligible = [a for a in aspects if a.rarity == rarity_name and not a.locked]

        if len(eligible) < required:
            await query.answer(ASPECT_RECYCLE_FAILURE_NOT_ENOUGH, show_alert=True)
            try:
                await query.edit_message_text(ASPECT_RECYCLE_FAILURE_NOT_ENOUGH)
            except Exception:
                pass
            return

        aspects_to_burn = random.sample(eligible, required)
        aspect_names = [html.escape(a.display_name) for a in aspects_to_burn]

        await query.answer()
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        # Start generating the upgraded aspect in background
        generation_task = asyncio.create_task(
            asyncio.to_thread(
                rolling.generate_aspect_for_chat,
                chat_id_str,
                gemini_util,
                upgrade_rarity,
                max_retries=MAX_BOT_IMAGE_RETRIES,
                source="roll",
            )
        )

        # Show burning animation
        for idx in range(len(aspects_to_burn)):
            text = build_burning_text(aspect_names, idx + 1)
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
                text=build_burning_text(aspect_names, len(aspects_to_burn), strike_all=True)
                + "\n\n♻️ Recycling...",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        try:
            generated_aspect = await generation_task
        except rolling.ImageGenerationError:
            event_service.log(
                EventType.RECYCLE,
                RecycleOutcome.ERROR,
                user_id=user.user_id,
                chat_id=chat_id_str,
                error_message="Image generation failed",
            )
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=ASPECT_RECYCLE_FAILURE_IMAGE,
            )
            return
        except Exception as exc:
            logger.error("Error while generating recycled aspect: %s", exc)
            event_service.log(
                EventType.RECYCLE,
                RecycleOutcome.ERROR,
                user_id=user.user_id,
                chat_id=chat_id_str,
                error_message=str(exc),
            )
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=ASPECT_RECYCLE_FAILURE_UNEXPECTED,
            )
            return

        # Delete the burned aspects via the service
        aspect_ids_to_delete = [a.id for a in aspects_to_burn]
        deleted = await asyncio.to_thread(
            aspect_service.recycle_aspects, aspect_ids_to_delete, user.user_id
        )

        if not deleted:
            logger.error(
                "recycle_aspects validation failed for user %s, aspect_ids=%s",
                user.user_id,
                aspect_ids_to_delete,
            )
            event_service.log(
                EventType.RECYCLE,
                RecycleOutcome.ERROR,
                user_id=user.user_id,
                chat_id=chat_id_str,
                error_message="recycle_aspects validation failed",
            )
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=ASPECT_RECYCLE_FAILURE_NOT_ENOUGH,
            )
            return

        # Claim the newly generated aspect for the user
        owner_username = user.username or f"user_{user.user_id}"
        claimed = await asyncio.to_thread(
            aspect_service.try_claim_aspect,
            generated_aspect.aspect_id,
            user.user_id,
            owner_username,
            chat_id_str,
        )
        if not claimed:
            logger.warning(
                "Failed to assign recycled aspect %s to user %s (%s)",
                generated_aspect.aspect_id,
                owner_username,
                user.user_id,
            )

        # Log recycle success
        event_service.log(
            EventType.RECYCLE,
            RecycleOutcome.SUCCESS,
            user_id=user.user_id,
            chat_id=chat_id_str,
            aspect_id=generated_aspect.aspect_id,
            source_rarity=rarity_name,
            new_rarity=upgrade_rarity,
            aspects_burned=aspect_ids_to_delete,
        )

        burned_block = "\n".join([f"<s>🔥🔮 {name}🔥</s>" for name in aspect_names])

        final_caption = ASPECT_CAPTION_BASE.format(
            aspect_id=generated_aspect.aspect_id,
            aspect_name=html.escape(generated_aspect.aspect_name),
            rarity=generated_aspect.rarity,
            set_name=(generated_aspect.set_name or "").title(),
        )
        final_caption += f"\n\nBurned aspects:\n\n<b>{burned_block}</b>\n\n"

        media = InputMediaPhoto(
            media=base64.b64decode(generated_aspect.image_b64),
            caption=final_caption,
            parse_mode=ParseMode.HTML,
        )

        # Build View in app button if MINIAPP_URL is configured
        reply_markup = None
        if MINIAPP_URL_ENV:
            aspect_token = encode_single_card_token(generated_aspect.aspect_id)
            aspect_url = f"{MINIAPP_URL_ENV}?startapp={aspect_token}"
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton(SLOTS_VIEW_IN_APP_LABEL, url=aspect_url)]]
            )

        await context.bot.edit_message_media(
            chat_id=chat_id,
            message_id=message_id,
            media=media,
            reply_markup=reply_markup,
        )

    finally:
        recycling_users.discard(user.user_id)
