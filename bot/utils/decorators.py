import asyncio
import logging
from functools import wraps
from typing import Any, Awaitable, Callable

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from . import database

HandlerFunc = Callable[..., Awaitable[Any]]

logger = logging.getLogger(__name__)


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

        db_user = await asyncio.to_thread(database.get_user, user.id)
        if not db_user:
            await _notify_user(update, context, registration_prompt)
            return None

        kwargs.setdefault("db_user", db_user)
        return await handler(update, context, *args, **kwargs)

    return wrapper


def verify_user_in_chat(handler: HandlerFunc) -> HandlerFunc:
    """Ensure the user is enrolled in the current chat."""

    enrollment_prompt = "You're not enrolled in this chat yet. Use /enroll in this chat to join."
    registration_prompt = "Please DM the bot with /start to register before using this command."

    @wraps(handler)
    async def inner(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat = update.effective_chat

        if not chat or chat.type == ChatType.PRIVATE:
            return await handler(update, context, *args, **kwargs)

        db_user = kwargs.get("db_user")
        if db_user is None:
            user = update.effective_user
            if not user or user.id is None:
                await _notify_user(update, context, "I couldn't identify your Telegram account.")
                return None

            db_user = await asyncio.to_thread(database.get_user, user.id)
            if not db_user:
                await _notify_user(update, context, registration_prompt)
                return None
            kwargs["db_user"] = db_user

        chat_id = str(chat.id)
        is_member = await asyncio.to_thread(database.is_user_in_chat, chat_id, db_user.user_id)
        if is_member:
            return await handler(update, context, *args, **kwargs)

        await _notify_user(update, context, enrollment_prompt)
        return None

    return verify_user(inner)
