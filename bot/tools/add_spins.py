"""Add spins to all users in a specific chat and notify them.

Usage:
    python bot/tools/add_spins.py --chat-id <chat_id> --count <count>
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram.ext import Application

# Ensure project root is on sys.path for module imports
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent  # tools -> bot
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Now that the path is correct, we can import from the bot directory
from utils.database import connect  # noqa: E402

# Determine if running in debug mode
DEBUG_MODE = os.getenv("DEBUG", "").lower() in ("true", "1", "yes")

# Load environment variables from the correct path
load_dotenv(dotenv_path=PROJECT_ROOT.parent / ".env", override=False)

# Use debug token when in debug mode, otherwise use production token
if DEBUG_MODE:
    TELEGRAM_TOKEN = os.getenv("DEBUG_TELEGRAM_AUTH_TOKEN")
else:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_AUTH_TOKEN")


async def send_notification(chat_id: int, count: int) -> None:
    """Send a notification message to the specified chat."""
    if not TELEGRAM_TOKEN:
        print("Error: Telegram token not found. Cannot send notification.")
        return

    builder = Application.builder().token(TELEGRAM_TOKEN)
    if DEBUG_MODE:
        # Use test environment for debug mode
        builder.base_url("https://api.telegram.org/bot")
        builder.base_file_url("https://api.telegram.org/file/bot")

    app = builder.build()

    if DEBUG_MODE:
        # Manually set the test environment URL for the bot instance
        app.bot._base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/test"
        app.bot._base_file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/test"

    message = f"{count} spins added to all accounts! Happy gambling 🎰"
    try:
        await app.bot.send_message(chat_id=chat_id, text=message)
        print(f"Successfully sent notification to chat {chat_id}.")
    except Exception as e:
        print(f"Failed to send notification to chat {chat_id}: {e}")


def main() -> None:
    """Add spins to users in a specific chat."""
    parser = argparse.ArgumentParser(description="Add spins to users in a specific chat.")
    parser.add_argument("--chat-id", type=int, required=True, help="The ID of the chat to update.")
    parser.add_argument("--count", type=int, required=True, help="The number of spins to add.")
    args = parser.parse_args()

    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE spins
        SET count = count + ?
        WHERE chat_id = ?
        """,
        (args.count, str(args.chat_id)),
    )
    updated_rows = cursor.rowcount
    conn.commit()
    conn.close()

    print(f"Added {args.count} spins to {updated_rows} users in chat {args.chat_id}.")

    # Send notification
    if updated_rows > 0:
        asyncio.run(send_notification(args.chat_id, args.count))


if __name__ == "__main__":
    main()
