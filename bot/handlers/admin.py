"""
Admin-only command handlers.

This module contains handlers for admin commands like adding spins,
reloading cache, and setting thread IDs.
"""

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from config import ADMIN_USERNAME
from utils.services import user_service, spin_service, card_service, thread_service
from utils.schemas import User
from utils.decorators import verify_admin, verify_user_in_chat

logger = logging.getLogger(__name__)


@verify_admin
async def spins(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Add spins to a specific user or all members of the current chat. Admin only."""
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
    if not context.args or len(context.args) < 1 or len(context.args) > 2:
        await message.reply_text(
            "Usage: /spins <number> [username]\n\n"
            "Examples:\n"
            "  /spins 5          - Add 5 spins to all users\n"
            "  /spins 10 @john   - Add 10 spins to @john",
            "  /spins @john 10   - Same as above",
            reply_to_message_id=message.message_id,
        )
        return

    # Parse arguments - can be either "/spins <amount>" or "/spins <username> <amount>"
    # Try parsing first arg as number, if it works use that format
    # Otherwise try second format
    target_username = None
    spins_to_add = None

    try:
        # Try format: /spins <amount>
        spins_to_add = int(context.args[0])
        if len(context.args) == 2:
            # Format: /spins <amount> <username>
            target_username = context.args[1].lstrip("@")
    except ValueError:
        # Try format: /spins <username> <amount>
        if len(context.args) == 2:
            target_username = context.args[0].lstrip("@")
            try:
                spins_to_add = int(context.args[1])
            except ValueError:
                await message.reply_text(
                    "The number of spins must be a valid integer.",
                    reply_to_message_id=message.message_id,
                )
                return
        else:
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

        if target_username:
            # Add spins to a specific user
            target_user_id = await asyncio.to_thread(
                user_service.get_user_id_by_username, target_username
            )

            if target_user_id is None:
                await message.reply_text(
                    f"User @{target_username} not found.",
                    reply_to_message_id=message.message_id,
                )
                return

            # Check if user is enrolled in this chat
            is_member = await asyncio.to_thread(
                user_service.is_user_in_chat, chat_id, target_user_id
            )

            if not is_member:
                await message.reply_text(
                    f"User @{target_username} is not enrolled in this chat.",
                    reply_to_message_id=message.message_id,
                )
                return

            # Add spins to the target user
            new_total = await asyncio.to_thread(
                spin_service.increment_user_spins, target_user_id, chat_id, spins_to_add
            )

            plural = "spin" if spins_to_add == 1 else "spins"
            await message.reply_text(
                f"✅ Successfully added {spins_to_add} {plural} to @{target_username}!\n\n"
                f"New balance: {new_total} {plural}\n\n"
                f"Use /casino -- happy gambling! 🎰",
                reply_to_message_id=message.message_id,
            )

            logger.info(
                f"@{user.username} executed /spins {spins_to_add} @{target_username} command"
            )
        else:
            # Add spins to all users in the chat
            all_user_ids = await asyncio.to_thread(user_service.get_all_chat_users, chat_id)

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
                        spin_service.increment_user_spins, user_id, chat_id, spins_to_add
                    )
                    successful_count += 1
                except Exception as e:
                    logger.warning(f"Failed to add spins to user {user_id}: {e}")

            # Report results
            plural = "spin" if spins_to_add == 1 else "spins"
            user_plural = "user" if successful_count == 1 else "users"

            await message.reply_text(
                f"✅ Successfully added {spins_to_add} {plural} to {successful_count} {user_plural} in this chat!\n\nUse /casino -- happy gambling! 🎰",
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
    user: User,
) -> None:
    """Reload command - clears all file_ids. Only accessible to admin."""
    # Silently ignore if user is not the admin
    if not ADMIN_USERNAME or user.username != ADMIN_USERNAME:
        return

    try:
        # Clear all file_ids from database
        affected_rows = await asyncio.to_thread(card_service.clear_all_file_ids)

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
    user: User,
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
            success = await asyncio.to_thread(thread_service.clear_thread_ids, chat_id)
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

        success = await asyncio.to_thread(
            thread_service.set_thread_id, chat_id, thread_id, thread_type
        )

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
