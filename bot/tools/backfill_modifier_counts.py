"""Backfill modifier_counts table from existing cards.

This script populates the modifier_counts table by aggregating modifier usage
from all existing cards in the database. Run this once after creating the
modifier_counts table to initialize historical data.

Usage:
    python tools/backfill_modifier_counts.py

Options:
    --dry-run    Show what would be inserted without making changes
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root is on sys.path for module imports
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

from sqlalchemy import func  # noqa: E402
from utils.session import get_session  # noqa: E402
from utils.models import CardModel, ModifierCountModel  # noqa: E402


def backfill_modifier_counts(dry_run: bool = False) -> None:
    """
    Backfill modifier_counts table from existing cards.

    Args:
        dry_run: If True, print what would be done without making changes.
    """
    print("Querying cards for modifier counts...")

    with get_session() as session:
        # Aggregate cards by (chat_id, season_id, modifier)
        results = (
            session.query(
                CardModel.chat_id,
                CardModel.season_id,
                CardModel.modifier,
                func.count().label("count"),
            )
            .filter(
                CardModel.chat_id.isnot(None),
                CardModel.modifier.isnot(None),
            )
            .group_by(
                CardModel.chat_id,
                CardModel.season_id,
                CardModel.modifier,
            )
            .all()
        )

    print(f"Found {len(results)} unique (chat_id, season_id, modifier) combinations.")

    if dry_run:
        print("\n[DRY RUN] Would insert the following counts:")
        for row in results:
            print(
                f"  chat_id={row.chat_id}, season_id={row.season_id}, "
                f"modifier={row.modifier!r}, count={row.count}"
            )
        print(f"\nTotal: {len(results)} rows would be inserted.")
        return

    # Clear existing counts and insert fresh data
    print("Clearing existing modifier_counts...")
    with get_session(commit=True) as session:
        session.query(ModifierCountModel).delete()

    print("Inserting new modifier counts...")
    inserted = 0
    with get_session(commit=True) as session:
        for row in results:
            record = ModifierCountModel(
                chat_id=str(row.chat_id),
                season_id=row.season_id,
                modifier=row.modifier,
                count=row.count,
            )
            session.add(record)
            inserted += 1

    print(f"Successfully inserted {inserted} modifier count records.")

    # Print summary by season
    print("\nSummary by season:")
    season_counts: dict[int, int] = defaultdict(int)
    for row in results:
        season_counts[row.season_id] += row.count

    for season_id, total in sorted(season_counts.items()):
        print(f"  Season {season_id}: {total} total cards")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill modifier_counts table from existing cards."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be inserted without making changes.",
    )
    args = parser.parse_args()

    backfill_modifier_counts(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
