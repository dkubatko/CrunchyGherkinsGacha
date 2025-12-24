"""
User-related command handlers.

This module contains handlers for user registration, profile management,
enrollment in chats, and character management (admin only).
"""

import asyncio
import base64
import logging
from io import BytesIO

from telegram import Update, InputMediaPhoto, ReactionTypeEmoji
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from config import ADMIN_USERNAME, DEBUG_MODE
from settings.constants import REACTION_IN_PROGRESS
from utils.services import user_service, character_service
from utils.schemas import User
from utils.decorators import verify_user

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register the user in the users table. DM-only."""
    message = update.message
    user = update.effective_user

    if not message or not user:
        return

    if update.effective_chat.type != ChatType.PRIVATE:
        await message.reply_text("Please DM me with /start to register.")
        return

    if not user.username:
        await message.reply_text(
            "You need a Telegram username to register. Please set one in Telegram settings and try again."
        )
        return

    user_exists = await asyncio.to_thread(user_service.user_exists, user.id)

    display_name = None
    if not user_exists:
        display_name = user.full_name or user.username

    await asyncio.to_thread(user_service.upsert_user, user.id, user.username, display_name, None)

    if user_exists:
        await message.reply_text("You're already registered! You're good to go.")
    else:
        await message.reply_text(
            "Welcome! You're registered and ready to play. Use /profile with a photo to personalize your card."
        )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display current profile info (no args) or update user's profile in DM, or add a character in group chats."""

    message = update.message
    user = update.effective_user

    if not message or not user:
        return

    # Check if it's a group chat or DM
    if update.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        # Group chat - add character functionality (admin only)
        # Check if user is admin
        if not ADMIN_USERNAME or user.username != ADMIN_USERNAME:
            await message.reply_text(
                "Only the bot administrator can add characters in group chats."
            )
            return

        command_text = message.text or message.caption or ""
        parts = command_text.split(maxsplit=1)

        if len(parts) < 2 or not parts[1].strip():
            await message.reply_text(
                "Usage: /profile <character_name> (attach a photo with the command).\n\nTo view your profile, please DM me with /profile (no arguments)."
            )
            return

        character_name = parts[1].strip()

        if not message.photo:
            await message.reply_text(
                "Please attach a character image when using /profile in group chats."
            )
            return

        photo = message.photo[-1]
        telegram_file = await context.bot.get_file(photo.file_id)
        buffer = BytesIO()
        await telegram_file.download_to_memory(out=buffer)
        image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        # Set thinking reaction while processing
        if not DEBUG_MODE:
            await context.bot.set_message_reaction(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                reaction=[ReactionTypeEmoji(REACTION_IN_PROGRESS)],
            )

        try:
            chat_id = str(update.effective_chat.id)
            existing_character = await asyncio.to_thread(
                character_service.get_character_by_name, chat_id, character_name
            )

            if existing_character:
                updated = await asyncio.to_thread(
                    character_service.update_character_image, existing_character.id, image_b64
                )

                if updated:
                    await message.reply_text(
                        f"Character '{character_name}' updated! Existing ID {existing_character.id} now has the new image."
                    )
                else:
                    await message.reply_text(
                        "I couldn't update that character's image. Please try again or delete and re-add it."
                    )
            else:
                character_id = await asyncio.to_thread(
                    character_service.add_character, chat_id, character_name, image_b64
                )

                await message.reply_text(
                    f"Character '{character_name}' added with ID {character_id}! They will now be used for card generation."
                )
        finally:
            # Remove thinking reaction
            if not DEBUG_MODE:
                await context.bot.set_message_reaction(
                    chat_id=update.effective_chat.id,
                    message_id=update.message.message_id,
                    reaction=[],
                )
        return

    # DM functionality - existing user profile update
    if update.effective_chat.type != ChatType.PRIVATE:
        await message.reply_text("Please DM me to update your profile.")
        return

    if not user.username:
        await message.reply_text("Please set a Telegram username before updating your profile.")
        return

    exists = await asyncio.to_thread(user_service.user_exists, user.id)
    if not exists:
        await message.reply_text("Please send /start first so I can register you.")
        return

    command_text = message.text or message.caption or ""
    parts = command_text.split(maxsplit=1)

    # Handle /profile with no arguments - show current profile
    if len(parts) < 2 or not parts[1].strip():
        # Get user's current profile data
        user_data = await asyncio.to_thread(user_service.get_user, user.id)

        if not user_data or not user_data.display_name:
            await message.reply_text(
                "You don't have a profile set up yet.\nUsage: /profile <display_name> (attach a photo with the command)."
            )
            return

        # Build response message
        profile_text = f"👤 <b>Your Profile</b>\n\n"
        profile_text += f"Display Name: <b>{user_data.display_name}</b>\n"
        profile_text += f"Username: @{user_data.username}"

        # Prepare media to send
        media_group = []

        if user_data.profile_imageb64:
            profile_image_data = base64.b64decode(user_data.profile_imageb64)
            profile_media = InputMediaPhoto(media=profile_image_data, caption="🖼️ Profile Image")
            media_group.append(profile_media)

        if user_data.slot_iconb64:
            slot_icon_data = base64.b64decode(user_data.slot_iconb64)
            slot_media = InputMediaPhoto(media=slot_icon_data, caption="🎰 Slot Machine Icon")
            media_group.append(slot_media)

        # Send response
        if media_group:
            # Send profile text first
            await message.reply_text(profile_text, parse_mode=ParseMode.HTML)
            # Then send images
            await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media_group)
        else:
            profile_text += "\n\n📷 No profile image available"
            await message.reply_text(profile_text, parse_mode=ParseMode.HTML)

        return

    display_name = parts[1].strip()

    if not message.photo:
        await message.reply_text("Please attach a profile image when using /profile.")
        return

    photo = message.photo[-1]
    telegram_file = await context.bot.get_file(photo.file_id)
    buffer = BytesIO()
    await telegram_file.download_to_memory(out=buffer)
    image_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    # Set thinking reaction while processing
    if not DEBUG_MODE:
        await context.bot.set_message_reaction(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
            reaction=[ReactionTypeEmoji(REACTION_IN_PROGRESS)],
        )

    try:
        await asyncio.to_thread(user_service.upsert_user, user.id, user.username, None, None)
        await asyncio.to_thread(user_service.update_user_profile, user.id, display_name, image_b64)

        await message.reply_text("Profile updated! Your new display name and image are saved.")
    finally:
        # Remove thinking reaction
        if not DEBUG_MODE:
            await context.bot.set_message_reaction(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                reaction=[],
            )


async def delete_character(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete characters by name (case-insensitive). Admin only."""

    message = update.message
    user = update.effective_user

    if not message or not user:
        return

    # Restrict to admin only
    # Check if user is admin
    if not ADMIN_USERNAME or user.username != ADMIN_USERNAME:
        await message.reply_text("Only the bot administrator can delete characters.")
        return

    if not context.args or len(context.args) != 1:
        await message.reply_text("Usage: /delete <character_name>")
        return

    character_name = context.args[0].strip()

    if not character_name:
        await message.reply_text("Character name cannot be empty.")
        return

    deleted_count = await asyncio.to_thread(
        character_service.delete_characters_by_name, character_name
    )

    if deleted_count == 0:
        await message.reply_text(f"No characters found with the name '{character_name}'.")
    elif deleted_count == 1:
        await message.reply_text(f"Deleted 1 character named '{character_name}'.")
    else:
        await message.reply_text(f"Deleted {deleted_count} characters named '{character_name}'.")


@verify_user
async def enroll(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Add the calling user to the current chat."""

    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("/enroll can only be used in group chats.")
        return

    chat_id = str(chat.id)
    is_member = await asyncio.to_thread(user_service.is_user_in_chat, chat_id, user.user_id)

    if is_member:
        await message.reply_text("You're already enrolled in this chat.")
        return

    inserted = await asyncio.to_thread(user_service.add_user_to_chat, chat_id, user.user_id)

    if inserted:
        await message.reply_text("You're enrolled! Have fun out there.")
    else:
        await message.reply_text("You're now marked as part of this chat.")

    missing_parts = []
    if not user.display_name:
        missing_parts.append("display name")
    if not user.profile_imageb64:
        missing_parts.append("profile photo")

    if missing_parts:
        prompt = (
            "Heads up: I don't have your "
            + " and ".join(missing_parts)
            + ". DM me with /profile <display_name> and a photo to complete your profile."
        )
        await message.reply_text(prompt)


@verify_user
async def unenroll(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: User,
) -> None:
    """Remove the calling user from the current chat."""

    message = update.message
    chat = update.effective_chat

    if not message or not chat:
        return

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text("/unenroll can only be used in group chats.")
        return

    chat_id = str(chat.id)
    is_member = await asyncio.to_thread(user_service.is_user_in_chat, chat_id, user.user_id)

    if not is_member:
        await message.reply_text("You're not enrolled in this chat.")
        return

    removed = await asyncio.to_thread(user_service.remove_user_from_chat, chat_id, user.user_id)

    if removed:
        await message.reply_text(
            "You're unenrolled from this chat. Use /enroll to rejoin anytime.",
        )
    else:
        await message.reply_text("You're no longer marked as part of this chat.")
