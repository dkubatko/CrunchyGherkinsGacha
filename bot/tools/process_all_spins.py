"""Process all spins for a user and generate cards for each win.

This tool simulates the slot machine for all of a user's available spins,
calculates results using the same logic as the /slots/verify endpoint,
and generates cards for each win with parallel processing (5 workers).

Usage:
    python bot/tools/process_all_spins.py <username> [--dry-run] [--debug]

Example:
    python bot/tools/process_all_spins.py matulka
    python bot/tools/process_all_spins.py matulka --dry-run
    python bot/tools/process_all_spins.py matulka --debug
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import os
import random
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

# Ensure project root is on sys.path for module imports
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent  # tools -> bot
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables - try multiple locations
load_dotenv()  # Current directory or parent directories
load_dotenv(dotenv_path=PROJECT_ROOT.parent / ".env", override=False)

# Determine if running in debug mode
DEBUG_MODE = os.getenv("DEBUG", "").lower() in ("true", "1", "yes")

# Use debug token when in debug mode, otherwise use production token
if DEBUG_MODE:
    TELEGRAM_TOKEN = os.getenv("DEBUG_TELEGRAM_AUTH_TOKEN")
    MINIAPP_URL = os.getenv("DEBUG_MINIAPP_URL")
else:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_AUTH_TOKEN")
    MINIAPP_URL = os.getenv("MINIAPP_URL")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
IMAGE_GEN_MODEL = os.getenv("IMAGE_GEN_MODEL")

# Now that the path is correct, we can import from the bot directory
from settings.constants import SLOT_CLAIM_CHANCE, SLOT_WIN_CHANCE
from utils import database
from utils.gemini import GeminiUtil
from utils.miniapp import encode_single_card_token
from utils.rolling import get_random_rarity
from utils.services import (
    card_service,
    character_service,
    claim_service,
    spin_service,
    thread_service,
    user_service,
)

# Initialize database
database.initialize_database()

# Number of parallel workers for card generation
NUM_WORKERS = 3

# Thread-safe print lock
print_lock = threading.Lock()


def safe_print(msg: str) -> None:
    """Thread-safe print."""
    with print_lock:
        print(msg)


@dataclass
class SpinResult:
    """Result of a single spin."""

    spin_index: int
    is_win: bool
    win_type: str  # "card", "claim", or "loss"
    rarity: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    source_name: Optional[str] = None


@dataclass
class ProcessingStats:
    """Statistics from processing all spins."""

    total_spins: int = 0
    card_wins: int = 0
    claim_wins: int = 0
    losses: int = 0
    cards_generated: int = 0
    cards_failed: int = 0
    cards_by_rarity: dict = field(default_factory=dict)
    cards_by_source: dict = field(default_factory=dict)


def create_bot_instance() -> Bot:
    """Create a Telegram Bot instance with appropriate configuration."""
    if not TELEGRAM_TOKEN:
        raise RuntimeError("Telegram token not available")

    if DEBUG_MODE:
        bot = Bot(token=TELEGRAM_TOKEN)
        bot._base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/test"
        bot._base_file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/test"
        return bot
    else:
        # Use local Telegram Bot API server in production
        api_base_url = "http://localhost:8081"
        return Bot(
            token=TELEGRAM_TOKEN,
            base_url=f"{api_base_url}/bot",
            base_file_url=f"{api_base_url}/file/bot",
            local_mode=True,
        )


def build_single_card_url(card_id: int) -> str:
    """Build a URL for viewing a single card in the mini app."""
    if not MINIAPP_URL:
        return ""

    import urllib.parse

    share_token = encode_single_card_token(card_id)
    separator = "&" if "?" in MINIAPP_URL else "?"
    return f"{MINIAPP_URL}{separator}startapp={urllib.parse.quote(share_token)}"


def get_eligible_sources(chat_id: str) -> List[dict]:
    """Get all eligible sources (users and characters) for a chat."""
    sources = user_service.get_chat_users_and_characters(chat_id)
    # Filter out sources without slot icons (they can't be used in slots)
    return [s for s in sources if s.get("slot_iconb64")]


def simulate_spin(
    spin_index: int, eligible_sources: List[dict], debug_mode: bool = False
) -> SpinResult:
    """Simulate a single spin using the same logic as /slots/verify."""
    if not eligible_sources:
        return SpinResult(spin_index=spin_index, is_win=False, win_type="loss")

    # Server-side win rate from config (boosted in debug mode)
    win_chance = 0.2 if debug_mode else SLOT_WIN_CHANCE
    is_card_win = random.random() < win_chance

    if is_card_win:
        # Pick a random eligible source
        source = random.choice(eligible_sources)
        rarity = get_random_rarity()
        return SpinResult(
            spin_index=spin_index,
            is_win=True,
            win_type="card",
            rarity=rarity,
            source_type=source["type"],
            source_id=source["id"],
            source_name=source.get("display_name", "Unknown"),
        )

    # Check for claim win
    claim_chance = 0.5 if debug_mode else SLOT_CLAIM_CHANCE
    if random.random() < claim_chance:
        return SpinResult(spin_index=spin_index, is_win=True, win_type="claim")

    return SpinResult(spin_index=spin_index, is_win=False, win_type="loss")


async def process_card_victory(
    bot: Bot,
    gemini_util: GeminiUtil,
    username: str,
    user_id: int,
    chat_id: str,
    result: SpinResult,
    semaphore: asyncio.Semaphore,
) -> Optional[int]:
    """Process a card victory: generate card, save to DB, send notification."""
    async with semaphore:
        from utils import rolling
        from settings.constants import SLOTS_VICTORY_RESULT_MESSAGE, SLOTS_VIEW_IN_APP_LABEL

        thread_id = thread_service.get_thread_id(chat_id)

        # Get source display name
        if result.source_type == "user":
            source_user = user_service.get_user(result.source_id)
            if not source_user or not source_user.display_name:
                safe_print(
                    f"  [Spin {result.spin_index}] ERROR: Source user {result.source_id} not found"
                )
                return None
            display_name = source_user.display_name
        else:
            source_character = character_service.get_character_by_id(result.source_id)
            if not source_character or not source_character.name:
                safe_print(
                    f"  [Spin {result.spin_index}] ERROR: Source character {result.source_id} not found"
                )
                return None
            display_name = source_character.name

        safe_print(
            f"  [Spin {result.spin_index}] Generating {result.rarity} card from {display_name}..."
        )

        # Send pending message
        pending_caption = (
            f"@{username} won a <b>{result.rarity} {display_name}</b> in slots!\n\n"
            "Generating card..."
        )

        send_params = {
            "chat_id": chat_id,
            "text": pending_caption,
            "parse_mode": ParseMode.HTML,
        }
        if thread_id is not None:
            send_params["message_thread_id"] = thread_id

        pending_message = await bot.send_message(**send_params)

        try:
            # Generate card (this is the slow part - runs in thread pool)
            generated_card = await asyncio.to_thread(
                rolling.generate_card_from_source,
                result.source_type,
                result.source_id,
                gemini_util,
                result.rarity,
                2,  # max_retries
                chat_id,
            )

            # Add card to database and assign to winner
            card_id = await asyncio.to_thread(
                card_service.add_card_from_generated, generated_card, chat_id
            )
            await asyncio.to_thread(card_service.set_card_owner, card_id, username, user_id)

            # Create final caption and keyboard
            final_caption = SLOTS_VICTORY_RESULT_MESSAGE.format(
                username=username,
                rarity=result.rarity,
                display_name=display_name,
                card_id=card_id,
                modifier=generated_card.modifier,
                base_name=generated_card.base_name,
            )

            card_url = build_single_card_url(card_id)
            keyboard = (
                InlineKeyboardMarkup(
                    [[InlineKeyboardButton(SLOTS_VIEW_IN_APP_LABEL, url=card_url)]]
                )
                if card_url
                else None
            )

            # Send the card image as a new message and delete the pending message
            card_image = base64.b64decode(generated_card.image_b64)

            photo_params = {
                "chat_id": chat_id,
                "photo": card_image,
                "caption": final_caption,
                "parse_mode": ParseMode.HTML,
            }
            if keyboard:
                photo_params["reply_markup"] = keyboard
            if thread_id is not None:
                photo_params["message_thread_id"] = thread_id

            card_message = await bot.send_photo(**photo_params)

            # Delete the pending message
            await bot.delete_message(chat_id=chat_id, message_id=pending_message.message_id)

            # Save the file_id from the card message
            if card_message.photo:
                file_id = card_message.photo[-1].file_id
                await asyncio.to_thread(card_service.update_card_file_id, card_id, file_id)

            safe_print(
                f"  [Spin {result.spin_index}] SUCCESS: Card {card_id} - {generated_card.modifier} {generated_card.base_name}"
            )
            return card_id

        except Exception as e:
            safe_print(f"  [Spin {result.spin_index}] FAILED: {e}")
            # Update pending message with failure
            failure_caption = (
                f"@{username} won a {result.rarity} {display_name} in slots!\n\n"
                "Card generation failed. Please try again later."
            )
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=pending_message.message_id,
                    text=failure_caption,
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            return None


async def process_all_spins(
    username: str,
    dry_run: bool = False,
) -> ProcessingStats:
    """Process all spins for a user."""
    stats = ProcessingStats()

    # Resolve user
    user_id = user_service.get_user_id_by_username(username)
    if not user_id:
        print(f"ERROR: User '{username}' not found")
        return stats

    # Get the user's most frequent chat
    chat_id = user_service.get_most_frequent_chat_id_for_user(user_id)
    if not chat_id:
        print(f"ERROR: No chat found for user '{username}'")
        return stats

    print(f"Processing spins for user '{username}' (ID: {user_id}) in chat {chat_id}")

    # Check if user is enrolled in chat
    if not user_service.is_user_in_chat(chat_id, user_id):
        print(f"ERROR: User '{username}' is not enrolled in chat {chat_id}")
        return stats

    # Get eligible sources for the chat
    eligible_sources = get_eligible_sources(chat_id)
    if not eligible_sources:
        print(f"ERROR: No eligible sources (users/characters with slot icons) in chat {chat_id}")
        return stats

    print(f"Found {len(eligible_sources)} eligible sources for slots")

    # Get current spin count
    current_spins = spin_service.get_or_update_user_spins_with_daily_refresh(user_id, chat_id)
    if current_spins <= 0:
        print(f"User '{username}' has no spins available")
        return stats

    stats.total_spins = current_spins
    print(f"User '{username}' has {current_spins} spins to process")

    # Initialize Gemini for image generation (only if not dry run)
    gemini_util = None
    bot = None
    if not dry_run:
        if not GOOGLE_API_KEY or not IMAGE_GEN_MODEL:
            print("ERROR: GOOGLE_API_KEY or IMAGE_GEN_MODEL not set")
            return stats
        gemini_util = GeminiUtil(GOOGLE_API_KEY, IMAGE_GEN_MODEL)
        bot = create_bot_instance()

    # Pre-simulate all spins to determine results
    print(f"\nSimulating {current_spins} spins...")
    spin_results: List[SpinResult] = []
    card_wins: List[SpinResult] = []

    for i in range(current_spins):
        result = simulate_spin(i + 1, eligible_sources, DEBUG_MODE)
        spin_results.append(result)

        if result.win_type == "card":
            stats.card_wins += 1
            stats.cards_by_rarity[result.rarity] = stats.cards_by_rarity.get(result.rarity, 0) + 1
            source_key = f"{result.source_type}:{result.source_name}"
            stats.cards_by_source[source_key] = stats.cards_by_source.get(source_key, 0) + 1
            card_wins.append(result)
        elif result.win_type == "claim":
            stats.claim_wins += 1
        else:
            stats.losses += 1

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"SPIN SIMULATION RESULTS FOR @{username}")
    print(f"{'=' * 60}")
    print(f"Total spins: {stats.total_spins}")
    print(f"Card wins: {stats.card_wins}")
    print(f"Claim wins: {stats.claim_wins}")
    print(f"Losses: {stats.losses}")
    print(f"\nCards by rarity:")
    for rarity, count in sorted(stats.cards_by_rarity.items()):
        print(f"  {rarity}: {count}")
    print(f"\nCards by source:")
    for source, count in sorted(stats.cards_by_source.items()):
        print(f"  {source}: {count}")
    print(f"{'=' * 60}\n")

    if dry_run:
        print("Dry run complete - no spins consumed or cards generated")
        return stats

    # Consume all spins
    print(f"Consuming {current_spins} spins...")
    spins_consumed = 0
    for _ in range(current_spins):
        if spin_service.consume_user_spin(user_id, chat_id):
            spins_consumed += 1
        else:
            print("WARNING: Failed to consume spin - may have run out")
            break
    print(f"Consumed {spins_consumed} spins")

    # Add claim points
    if stats.claim_wins > 0:
        print(f"Adding {stats.claim_wins} claim points...")
        claim_service.increment_claim_balance(user_id, chat_id, stats.claim_wins)

    # Process card wins in parallel with semaphore limiting to NUM_WORKERS
    if card_wins:
        print(f"\nGenerating {len(card_wins)} cards with {NUM_WORKERS} parallel workers...")
        semaphore = asyncio.Semaphore(NUM_WORKERS)

        tasks = [
            process_card_victory(bot, gemini_util, username, user_id, chat_id, result, semaphore)
            for result in card_wins
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                stats.cards_failed += 1
            elif r is not None:
                stats.cards_generated += 1
            else:
                stats.cards_failed += 1

    # Print final results
    print(f"\n{'=' * 60}")
    print(f"FINAL RESULTS")
    print(f"{'=' * 60}")
    print(f"Spins consumed: {spins_consumed}")
    print(f"Cards generated: {stats.cards_generated}/{stats.card_wins}")
    print(f"Cards failed: {stats.cards_failed}")
    print(f"Claim points added: {stats.claim_wins}")
    print(f"{'=' * 60}")

    return stats


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Process all spins for a user and generate cards for wins."
    )
    parser.add_argument("username", type=str, help="Username to process spins for (without @)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate spins without consuming or generating cards",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Force debug mode (use Telegram test API instead of local server)",
    )
    args = parser.parse_args()

    # Override DEBUG_MODE if --debug flag is passed
    global DEBUG_MODE, TELEGRAM_TOKEN, MINIAPP_URL
    if args.debug:
        DEBUG_MODE = True
        TELEGRAM_TOKEN = os.getenv("DEBUG_TELEGRAM_AUTH_TOKEN")
        MINIAPP_URL = os.getenv("DEBUG_MINIAPP_URL")

    # Remove @ prefix if provided
    username = args.username.lstrip("@")

    asyncio.run(process_all_spins(username, args.dry_run))


if __name__ == "__main__":
    main()
