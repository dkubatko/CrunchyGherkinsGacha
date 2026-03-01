"""Send a custom message to a specified Telegram chat.

Usage:
    python bot/tools/send_message.py --chat-id <chat_id> --text "Your message here"
    python bot/tools/send_message.py --chat-id <chat_id> --file message.txt
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram.ext import Application
from telegram.constants import ParseMode

# Ensure project root is on sys.path for module imports
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent  # tools -> bot
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Determine if running in debug mode
DEBUG_MODE = os.getenv("DEBUG", "").lower() in ("true", "1", "yes")

# Load environment variables from the correct path
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

# Use debug token when in debug mode, otherwise use production token
if DEBUG_MODE:
    TELEGRAM_TOKEN = os.getenv("DEBUG_TELEGRAM_AUTH_TOKEN")
else:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_AUTH_TOKEN")


async def send_message(chat_id: int, text: str, use_html: bool = False) -> None:
    """Send a message to the specified chat."""
    if not TELEGRAM_TOKEN:
        print("Error: Telegram token not found. Check your .env file.")
        return

    builder = Application.builder().token(TELEGRAM_TOKEN)
    if DEBUG_MODE:
        builder.base_url("https://api.telegram.org/bot")
        builder.base_file_url("https://api.telegram.org/file/bot")

    app = builder.build()

    if DEBUG_MODE:
        app.bot._base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/test"
        app.bot._base_file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/test"

    # Get thread_id if the chat uses topics
    from utils.services import thread_service

    thread_id = thread_service.get_thread_id(str(chat_id))

    send_params: dict = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": ParseMode.HTML,
    }
    if thread_id is not None:
        send_params["message_thread_id"] = thread_id

    try:
        await app.bot.send_message(**send_params)
        print(
            f"Message sent to chat {chat_id}"
            + (f" (thread {thread_id})" if thread_id else "")
            + "."
        )
    except Exception as e:
        print(f"Failed to send message to chat {chat_id}: {e}")


def main() -> None:
    """Send a custom message to a Telegram chat."""
    parser = argparse.ArgumentParser(description="Send a custom message to a Telegram chat.")
    parser.add_argument("--chat-id", type=int, required=True, help="The ID of the chat.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", type=str, help="The message text to send.")
    group.add_argument("--file", type=str, help="Path to a text file containing the message.")
    args = parser.parse_args()

    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"Error: File not found: {args.file}")
            sys.exit(1)
        text = path.read_text(encoding="utf-8").rstrip("\n")
    else:
        text = args.text

    asyncio.run(send_message(chat_id=args.chat_id, text=text))


if __name__ == "__main__":
    main()
