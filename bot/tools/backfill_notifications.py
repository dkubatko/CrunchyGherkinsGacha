"""Backfill roll notifications for all user/chat pairs with existing rolls.

Creates a notification row for each user/chat in the user_rolls table that
doesn't already have one.  The notify_at is set to last_roll_timestamp + 24h.
Rows are always created as unsent — startup recovery will handle overdue ones.

Usage:
    python bot/tools/backfill_notifications.py [--dry-run]
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure bot/ is on sys.path for module imports
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent  # tools/ -> bot/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

# Imports after path/env setup
import argparse  # noqa: E402

from utils.database import run_migrations  # noqa: E402
from utils.models import RollNotificationModel, UserRollModel  # noqa: E402
from utils.session import get_session  # noqa: E402

ROLL_COOLDOWN = datetime.timedelta(hours=24)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill roll notifications from user_rolls data.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be inserted without writing to DB.",
    )
    args = parser.parse_args()

    # Ensure DB is up to date
    run_migrations()

    now = datetime.datetime.now(datetime.timezone.utc)

    with get_session(commit=not args.dry_run) as session:
        # All user/chat pairs that have rolled
        rolls = session.query(UserRollModel).all()
        print(f"Found {len(rolls)} user/chat roll records.")

        created = 0
        skipped = 0

        for roll in rolls:
            # Check if notification already exists
            existing = (
                session.query(RollNotificationModel)
                .filter(
                    RollNotificationModel.user_id == roll.user_id,
                    RollNotificationModel.chat_id == roll.chat_id,
                )
                .first()
            )
            if existing:
                skipped += 1
                continue

            notify_at = roll.last_roll_timestamp + ROLL_COOLDOWN

            if args.dry_run:
                status = "past due" if notify_at <= now else "future"
                print(
                    f"  [DRY RUN] user={roll.user_id} chat={roll.chat_id} "
                    f"notify_at={notify_at.isoformat()} ({status})"
                )
            else:
                notif = RollNotificationModel(
                    user_id=roll.user_id,
                    chat_id=roll.chat_id,
                    notify_at=notify_at,
                    sent=False,
                    attempt_count=0,
                )
                session.add(notif)

            created += 1

        print(f"Done. Created={created}, Skipped (already exist)={skipped}")


if __name__ == "__main__":
    main()
