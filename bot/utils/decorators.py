import asyncio
import logging
import sys
from functools import wraps
from typing import Any, Awaitable, Callable, Optional

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from utils.services import user_service

HandlerFunc = Callable[..., Awaitable[Any]]

logger = logging.getLogger(__name__)

# Check for debug mode at module level
DEBUG_MODE = "--debug" in sys.argv

# Admin username - must be set via set_admin_username() before using verify_admin
_admin_username: Optional[str] = None


def set_admin_username(username: str) -> None:
    """
    Set the admin username for the verify_admin decorator.

    This should be called once at application startup.

    Args:
        username: The admin username
    """
    global _admin_username
    _admin_username = username
    logger.info("Admin username configured")


def get_admin_username() -> Optional[str]:
    """Get the configured admin username."""
    return _admin_username


async def _notify_user(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    """Send a message or alert back to the user who triggered the update."""

    if update.callback_query:
        try:
            await update.callback_query.answer(message, show_alert=True)
        except Exception:
            pass
        if update.callback_query.message:
            await update.callback_query.message.reply_text(message)
        return

    if update.message:
        await update.message.reply_text(message)
        return

    chat = update.effective_chat
    if chat:
        try:
            await context.bot.send_message(chat_id=chat.id, text=message)
        except Exception:
            logger.debug("Unable to deliver prompt '%s' to chat %s", message, chat.id)


def verify_user(handler: HandlerFunc) -> HandlerFunc:
    """Ensure the calling user exists in the users table before proceeding."""

    registration_prompt = "Please DM the bot with /start to register before using this command."

    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or user.id is None:
            await _notify_user(update, context, "I couldn't identify your Telegram account.")
            return None

        db_user = await asyncio.to_thread(user_service.get_user, user.id)
        if not db_user:
            await _notify_user(update, context, registration_prompt)
            return None

        kwargs.setdefault("user", db_user)
        return await handler(update, context, *args, **kwargs)

    return wrapper


def verify_user_in_chat(handler: HandlerFunc) -> HandlerFunc:
    """Ensure the user is enrolled in the current chat."""

    enrollment_prompt = "You're not enrolled in this chat yet. Use /enroll in this chat to join."

    @verify_user
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat = update.effective_chat

        if not chat or chat.type == ChatType.PRIVATE:
            return await handler(update, context, *args, **kwargs)

        db_user = kwargs.get("user")
        if db_user is None:
            logger.warning(
                "verify_user_in_chat executed without user kwarg; was verify_user removed?"
            )
            await _notify_user(update, context, "I couldn't identify your Telegram account.")
            return None

        chat_id = str(chat.id)
        is_member = await asyncio.to_thread(user_service.is_user_in_chat, chat_id, db_user.user_id)
        if is_member:
            return await handler(update, context, *args, **kwargs)

        await _notify_user(update, context, enrollment_prompt)
        return None

    return wrapper


def verify_admin(handler: HandlerFunc) -> HandlerFunc:
    """Ensure the calling user is the bot administrator."""

    @verify_user
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        admin_username = get_admin_username()
        db_user = kwargs.get("user")

        if not admin_username:
            logger.warning("Admin username not configured")
            await _notify_user(update, context, "Admin functionality is not configured.")
            return None

        if not db_user or db_user.username != admin_username:
            # Silently ignore non-admin users (like the reload command)
            return None

        return await handler(update, context, *args, **kwargs)

    return wrapper


def prevent_concurrency(bot_data_key: str) -> Callable[[HandlerFunc], HandlerFunc]:
    """
    Prevent concurrent callback executions for the same user + resource combination.

    This decorator guards against rapid repeated button clicks by tracking in-progress
    operations in context.bot_data[bot_data_key]. Duplicate requests are silently dropped.

    The decorator extracts an ID from query.data by splitting on '_' and taking index 1.
    It builds a composite key as f"{user.user_id}_{resource_id}" to allow the same user
    to interact with different resources concurrently, while blocking duplicate clicks
    on the same resource.

    Must be used AFTER @verify_user_in_chat (which injects the 'user' kwarg).

    Args:
        bot_data_key: The key in context.bot_data where the set of in-progress
                      operations is stored (e.g., "pending_roll_actions").

    Example:
        @verify_user_in_chat
        @prevent_concurrency("pending_roll_actions")
        async def claim_card(update, context, user):
            ...
    """

    def decorator(handler: HandlerFunc) -> HandlerFunc:
        @wraps(handler)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            query = update.callback_query
            if not query or not query.data:
                return await handler(update, context, *args, **kwargs)

            db_user = kwargs.get("user")
            if not db_user:
                return await handler(update, context, *args, **kwargs)

            # Extract resource ID from callback data (e.g., "claim_123" -> "123")
            data_parts = query.data.split("_")
            if len(data_parts) < 2:
                return await handler(update, context, *args, **kwargs)

            resource_id = data_parts[1]
            action_key = f"{db_user.user_id}_{resource_id}"

            pending_actions = context.bot_data.setdefault(bot_data_key, set())

            if action_key in pending_actions:
                # Silently acknowledge and drop the duplicate request
                logger.warning(
                    "Dropping duplicate callback for user %s on resource %s (key: %s)",
                    db_user.user_id,
                    resource_id,
                    bot_data_key,
                )
                await query.answer()
                return None

            pending_actions.add(action_key)
            try:
                return await handler(update, context, *args, **kwargs)
            finally:
                pending_actions.discard(action_key)

        return wrapper

    return decorator
