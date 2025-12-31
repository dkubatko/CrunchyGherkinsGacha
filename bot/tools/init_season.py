"""Initialize a new season by resetting user progress.

Resets:
- Roll times (to midnight before today)
- Spin counts (to refresh at next refresh window)
- Megaspin progress (counter reset, megaspin not available)
- Minesweeper games (force expire active games)
- Claim points (reset to 1)

Usage:
    python bot/tools/init_season.py
    python bot/tools/init_season.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram.ext import Application
from telegram.constants import ParseMode

# Ensure project root is on sys.path for module imports
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent  # tools -> bot
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables BEFORE accessing them
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

# Now that the path is correct, we can import from the bot directory
from utils.session import get_session  # noqa: E402
from utils.models import (  # noqa: E402
    CardModel,
    ClaimModel,
    MegaspinsModel,
    MinesweeperGameModel,
    SpinsModel,
    UserRollModel,
)

# Determine if running in debug mode
DEBUG_MODE = os.getenv("DEBUG", "").lower() in ("true", "1", "yes")

# Use debug token when in debug mode, otherwise use production token
if DEBUG_MODE:
    TELEGRAM_TOKEN = os.getenv("DEBUG_TELEGRAM_AUTH_TOKEN")
else:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_AUTH_TOKEN")

# PDT timezone
PDT_TZ = ZoneInfo("America/Los_Angeles")

# Default values for reset
DEFAULT_CLAIM_BALANCE = 1
DEFAULT_SPINS_FOR_MEGASPIN = 100

# Season announcement message
SEASON_ANNOUNCEMENT = """Today marks the first day of <b>Season 1</b> of the <b>Crunchy Gherkins Gacha</b>!

This season includes comprehensive updates as well as a number of new features:
- 300+ fresh keywords
- New casino game: Ride the Bus!
- Megaspin &amp; autospin
- Unique /roll keywords
- Keyword sets
- Achievements

And many other improvements across the board. Please enjoy the new season!"""


def get_most_common_chat_id() -> str:
    """Get the most common chat_id from the cards table."""
    from sqlalchemy import func

    with get_session() as session:
        result = (
            session.query(CardModel.chat_id, func.count(CardModel.chat_id).label("count"))
            .filter(CardModel.chat_id.isnot(None))
            .group_by(CardModel.chat_id)
            .order_by(func.count(CardModel.chat_id).desc())
            .first()
        )

        if result is None:
            raise RuntimeError("No cards with chat_id found in the database")

        return result[0]


def get_season_start_timestamp() -> str:
    """Get the timestamp of December 31st, 2025 at 00:00:00 PDT."""
    season_start = datetime.datetime(2025, 12, 31, 0, 0, 0, tzinfo=PDT_TZ)
    return season_start.isoformat()


def reset_roll_times(chat_id: str, dry_run: bool = False) -> int:
    """Reset all roll times to season start for the specified chat."""
    season_start = get_season_start_timestamp()

    with get_session(commit=not dry_run) as session:
        rolls = session.query(UserRollModel).filter(UserRollModel.chat_id == str(chat_id)).all()

        count = 0
        for roll in rolls:
            if dry_run:
                print(
                    f"  [DRY-RUN] Would reset roll time for user {roll.user_id} to {season_start}"
                )
            else:
                roll.last_roll_timestamp = season_start
            count += 1

        return count


def reset_spins(chat_id: str, dry_run: bool = False) -> int:
    """Reset all spin refresh timestamps to season start."""
    season_start = get_season_start_timestamp()

    with get_session(commit=not dry_run) as session:
        spins = session.query(SpinsModel).filter(SpinsModel.chat_id == str(chat_id)).all()

        count = 0
        for spin in spins:
            if dry_run:
                print(
                    f"  [DRY-RUN] Would reset spin refresh for user {spin.user_id} to {season_start}"
                )
            else:
                spin.refresh_timestamp = season_start
            count += 1

        return count


def reset_megaspins(chat_id: str, dry_run: bool = False) -> int:
    """Reset all megaspin progress for the specified chat."""
    with get_session(commit=not dry_run) as session:
        megaspins = (
            session.query(MegaspinsModel).filter(MegaspinsModel.chat_id == str(chat_id)).all()
        )

        count = 0
        for megaspin in megaspins:
            if dry_run:
                print(
                    f"  [DRY-RUN] Would reset megaspin for user {megaspin.user_id}: "
                    f"spins_until_megaspin={DEFAULT_SPINS_FOR_MEGASPIN}, megaspin_available=False"
                )
            else:
                megaspin.spins_until_megaspin = DEFAULT_SPINS_FOR_MEGASPIN
                megaspin.megaspin_available = False
            count += 1

        return count


def expire_minesweeper_games(chat_id: str, dry_run: bool = False) -> int:
    """Expire all active minesweeper games for the specified chat."""
    season_start = get_season_start_timestamp()
    season_start_dt = datetime.datetime.fromisoformat(season_start)

    with get_session(commit=not dry_run) as session:
        games = (
            session.query(MinesweeperGameModel)
            .filter(
                MinesweeperGameModel.chat_id == str(chat_id),
                MinesweeperGameModel.status == "active",
            )
            .all()
        )

        count = 0
        for game in games:
            if dry_run:
                print(
                    f"  [DRY-RUN] Would expire minesweeper game {game.id} for user {game.user_id}"
                )
            else:
                game.status = "expired"
                game.last_updated_timestamp = season_start_dt
            count += 1

        return count


def reset_claim_points(chat_id: str, dry_run: bool = False) -> int:
    """Reset all claim points to default value for the specified chat."""
    with get_session(commit=not dry_run) as session:
        claims = session.query(ClaimModel).filter(ClaimModel.chat_id == str(chat_id)).all()

        count = 0
        for claim in claims:
            if dry_run:
                print(
                    f"  [DRY-RUN] Would reset claim balance for user {claim.user_id}: "
                    f"{claim.balance} -> {DEFAULT_CLAIM_BALANCE}"
                )
            else:
                claim.balance = DEFAULT_CLAIM_BALANCE
            count += 1

        return count


async def send_season_announcement(chat_id: int) -> None:
    """Send the season announcement message to the specified chat."""
    if not TELEGRAM_TOKEN:
        print("Error: Telegram token not found. Cannot send notification.")
        return

    builder = Application.builder().token(TELEGRAM_TOKEN)
    if DEBUG_MODE:
        builder.base_url("https://api.telegram.org/bot")
        builder.base_file_url("https://api.telegram.org/file/bot")

    app = builder.build()

    if DEBUG_MODE:
        app.bot._base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/test"
        app.bot._base_file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/test"

    # Get thread_id if available
    from utils.services import thread_service

    thread_id = thread_service.get_thread_id(str(chat_id))

    send_params = {
        "chat_id": chat_id,
        "text": SEASON_ANNOUNCEMENT,
        "parse_mode": ParseMode.HTML,
    }
    if thread_id is not None:
        send_params["message_thread_id"] = thread_id

    try:
        await app.bot.send_message(**send_params)
        print(
            f"Successfully sent season announcement to chat {chat_id}"
            + (f" (thread {thread_id})" if thread_id else "")
            + "."
        )
    except Exception as e:
        print(f"Failed to send season announcement to chat {chat_id}: {e}")


def main() -> None:
    """Initialize the new season by resetting all user progress."""
    parser = argparse.ArgumentParser(
        description="Initialize a new season by resetting user progress."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them.",
    )
    args = parser.parse_args()

    dry_run = args.dry_run

    # Get the most common chat_id from the cards table
    chat_id = get_most_common_chat_id()
    chat_id_int = int(chat_id)

    if dry_run:
        print("=" * 60)
        print("DRY-RUN MODE - No changes will be applied")
        print("=" * 60)

    print(f"\nInitializing Season 1 for chat {chat_id}...")
    print("-" * 40)

    # Reset roll times
    print("\n[1/5] Resetting roll times...")
    roll_count = reset_roll_times(chat_id, dry_run)
    print(f"  {'Would reset' if dry_run else 'Reset'} {roll_count} roll time(s)")

    # Reset spins
    print("\n[2/5] Resetting spin refresh times...")
    spin_count = reset_spins(chat_id, dry_run)
    print(f"  {'Would reset' if dry_run else 'Reset'} {spin_count} spin record(s)")

    # Reset megaspins
    print("\n[3/5] Resetting megaspin progress...")
    megaspin_count = reset_megaspins(chat_id, dry_run)
    print(f"  {'Would reset' if dry_run else 'Reset'} {megaspin_count} megaspin record(s)")

    # Expire minesweeper games
    print("\n[4/5] Expiring active minesweeper games...")
    minesweeper_count = expire_minesweeper_games(chat_id, dry_run)
    print(f"  {'Would expire' if dry_run else 'Expired'} {minesweeper_count} minesweeper game(s)")

    # Reset claim points
    print("\n[5/5] Resetting claim points...")
    claim_count = reset_claim_points(chat_id, dry_run)
    print(f"  {'Would reset' if dry_run else 'Reset'} {claim_count} claim balance(s)")

    # Summary
    print("\n" + "=" * 40)
    print("SUMMARY")
    print("=" * 40)
    print(f"  Roll times:        {roll_count}")
    print(f"  Spin records:      {spin_count}")
    print(f"  Megaspin records:  {megaspin_count}")
    print(f"  Minesweeper games: {minesweeper_count}")
    print(f"  Claim balances:    {claim_count}")

    if dry_run:
        print("\n[DRY-RUN] No changes were applied.")
        print("[DRY-RUN] Run without --dry-run to apply changes.")

    # Send season announcement (even in dry-run mode)
    print("\nSending season announcement...")
    asyncio.run(send_season_announcement(chat_id_int))
    print("\nSeason initialization complete!")


if __name__ == "__main__":
    main()
