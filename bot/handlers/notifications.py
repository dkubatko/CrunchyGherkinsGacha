"""Notification handler — PTB-aware notification scheduling and sending.

This module bridges the notification manager (PTB-free business logic)
with python-telegram-bot's JobQueue and Bot API. It handles:
- Scheduling one-shot jobs via job_queue.run_once()
- Sending DM notifications with deep link buttons
- Startup recovery for unsent notifications
"""

from __future__ import annotations

import asyncio
import datetime
import html
import logging
from typing import Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import Forbidden, RetryAfter
from telegram.ext import Application, CallbackContext

from managers import notification_manager
from repos import thread_repo

logger = logging.getLogger(__name__)

# Job name prefix for roll notification jobs
_JOB_NAME_PREFIX = "roll_notif"


def build_chat_link(
    chat_id: str, thread_id: Optional[int] = None,
) -> Optional[str]:
    """Build a t.me deep link for a supergroup chat thread.

    Returns None if no thread_id is available (non-topic chats have no
    reliable deep link format without a specific message ID).
    """
    if thread_id is None:
        return None

    # Strip -100 prefix from supergroup chat IDs
    # e.g. -1001234567890 -> 1234567890
    numeric_id = str(chat_id).lstrip("-")
    if numeric_id.startswith("100"):
        numeric_id = numeric_id[3:]

    return f"https://t.me/c/{numeric_id}/{thread_id}"


def _job_name(user_id: int, chat_id: str) -> str:
    """Generate a unique job name for a user/chat notification."""
    return f"{_JOB_NAME_PREFIX}_{user_id}_{chat_id}"


def schedule_notification(
    job_queue, user_id: int, chat_id: str, notify_at: datetime.datetime,
) -> None:
    """Schedule a one-shot notification job via JobQueue.

    Removes any existing job for the same user/chat pair first
    to avoid duplicates when a user re-rolls.

    This function is thread-safe — APScheduler's add_job() uses
    internal locks and call_soon_threadsafe for event loop wakeup.
    """
    name = _job_name(user_id, chat_id)

    # Remove any existing job for this user/chat pair
    existing_jobs = job_queue.get_jobs_by_name(name)
    for job in existing_jobs:
        job.schedule_removal()

    job_queue.run_once(
        _send_notification_callback,
        when=notify_at,
        name=name,
        data={
            "user_id": user_id,
            "chat_id": chat_id,
            "notify_at": notify_at.isoformat(),
        },
    )

    logger.debug(
        "Scheduled roll notification for user %d in chat %s at %s",
        user_id, chat_id, notify_at,
    )


async def _send_notification_callback(context: CallbackContext) -> None:
    """JobQueue callback that sends the actual DM notification."""
    data = context.job.data
    user_id = data["user_id"]
    chat_id = data["chat_id"]
    expected_notify_at = datetime.datetime.fromisoformat(data["notify_at"])

    await _send_single_notification(
        context.bot, user_id, chat_id, expected_notify_at,
    )


async def _send_single_notification(
    bot: Bot,
    user_id: int,
    chat_id: str,
    expected_notify_at: datetime.datetime,
) -> None:
    """Send a single roll-ready DM notification.

    Uses atomic claim_and_complete to check deliverability (enrollment +
    prefs + staleness) and mark as sent in one transaction. This prevents
    duplicate sends from concurrent workers.

    Thread ID for the deep link is looked up from ThreadModel at send time.
    """
    # Atomic: check deliverability + mark as sent in one transaction
    claimed = await asyncio.to_thread(
        notification_manager.claim_and_complete,
        user_id, chat_id, expected_notify_at,
    )

    if not claimed:
        logger.debug(
            "Notification for user %d chat %s not deliverable (opted out, "
            "unenrolled, already sent, or superseded by newer roll)",
            user_id, chat_id,
        )
        return

    # Look up thread from ThreadModel (source of truth)
    message_thread_id = await asyncio.to_thread(
        thread_repo.get_thread_id, str(chat_id),
    )

    # Get chat title
    chat_title = "the group"
    try:
        chat = await bot.get_chat(chat_id)
        if chat.title:
            chat_title = chat.title
    except Exception as e:
        logger.warning("Failed to get chat info for %s: %s", chat_id, e)

    # Build message with HTML-escaped title
    safe_title = html.escape(chat_title)
    text = (
        "🎲 <b>Your roll is ready!</b>\n\n"
        f"You can now /roll in <b>{safe_title}</b>."
    )

    # Build deep link button if thread available
    link = build_chat_link(str(chat_id), message_thread_id)
    reply_markup = None
    if link:
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="Go to chat →", url=link)]
        ])

    # Send DM — notification is already marked sent by claim_and_complete
    try:
        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )
        logger.info(
            "Sent roll notification to user %d for chat %s", user_id, chat_id,
        )
    except Forbidden:
        # User blocked the bot — already marked sent, just log
        logger.info(
            "User %d blocked bot, notification already marked sent", user_id,
        )
    except RetryAfter as e:
        logger.warning(
            "Rate limited sending to user %d, retrying in %ds",
            user_id, e.retry_after,
        )
        await asyncio.sleep(e.retry_after)
        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
            logger.info(
                "Sent roll notification to user %d for chat %s (after retry)",
                user_id, chat_id,
            )
        except Exception as retry_err:
            logger.error(
                "Failed to send notification to user %d after retry: %s",
                user_id, retry_err,
            )
    except Exception as e:
        logger.error(
            "Failed to send notification to user %d: %s", user_id, e,
        )


async def recover_pending_notifications(application: Application) -> None:
    """Startup recovery: send overdue notifications and re-schedule future ones.

    Called from post_init as a background task (asyncio.create_task) so
    it doesn't block bot startup.

    Recovery loads ALL unsent rows (no prefs/enrollment filter). The
    send path (_send_single_notification) does the deliverability check
    per-notification via atomic claim_and_complete.
    """
    bot = application.bot
    job_queue = application.job_queue

    logger.info("Starting notification recovery...")

    # 1. Send overdue notifications
    try:
        pending = await asyncio.to_thread(
            notification_manager.get_all_unsent_overdue,
        )
        if pending:
            logger.info("Found %d overdue notifications to send", len(pending))
            for i, notif in enumerate(pending):
                try:
                    await _send_single_notification(
                        bot, notif.user_id, notif.chat_id, notif.notify_at,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to send overdue notification for user %d chat %s: %s",
                        notif.user_id, notif.chat_id, e,
                    )
                # Rate limiting: pause every 30 messages
                if (i + 1) % 30 == 0:
                    await asyncio.sleep(1.0)
                else:
                    await asyncio.sleep(0.05)
    except Exception as e:
        logger.error("Error during overdue notification recovery: %s", e)

    # 2. Re-schedule future notifications
    try:
        future = await asyncio.to_thread(
            notification_manager.get_all_unsent_future,
        )
        if future:
            logger.info(
                "Re-scheduling %d future notifications", len(future),
            )
            for notif in future:
                try:
                    schedule_notification(
                        job_queue,
                        notif.user_id,
                        notif.chat_id,
                        notif.notify_at,
                    )
                except Exception as e:
                    logger.error(
                        "Failed to re-schedule notification for user %d chat %s: %s",
                        notif.user_id, notif.chat_id, e,
                    )
    except Exception as e:
        logger.error("Error during future notification re-scheduling: %s", e)

    logger.info("Notification recovery complete")
