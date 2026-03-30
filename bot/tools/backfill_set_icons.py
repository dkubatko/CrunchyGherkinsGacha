"""Backfill slot icons for all existing aspect sets.

Generates a casino-styled slot icon for each set that doesn't already have
one in the ``set_icons`` table, using the same Gemini pipeline as the admin
create-set flow.

Usage:
    python bot/tools/backfill_set_icons.py [--season-id N] [--dry-run]
"""

from __future__ import annotations

import argparse
import base64
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Ensure bot/ is on sys.path for module imports
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent  # tools/ -> bot/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

# Imports after path/env setup
from repos import set_repo, set_icon_repo  # noqa: E402
from utils.slot_icon import generate_set_slot_icon  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill set slot icons via Gemini.")
    parser.add_argument(
        "--season-id",
        type=int,
        default=None,
        help="Limit to a specific season (default: all seasons).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List sets that would be processed without generating anything.",
    )
    args = parser.parse_args()

    season_ids: list[int]
    if args.season_id is not None:
        season_ids = [args.season_id]
    else:
        season_ids = set_repo.get_available_seasons()

    total = 0
    generated = 0
    skipped = 0
    failed = 0

    for season_id in season_ids:
        sets = set_repo.get_sets_by_season(season_id=season_id)
        logger.info("Season %d: %d sets", season_id, len(sets))

        existing_icons = set_icon_repo.get_all_icons_b64(season_id=season_id)

        for s in sets:
            total += 1
            if s.id in existing_icons:
                logger.info("  [skip] Set #%d '%s' — icon already exists", s.id, s.name)
                skipped += 1
                continue

            if args.dry_run:
                logger.info("  [dry-run] Set #%d '%s' — would generate icon", s.id, s.name)
                continue

            logger.info("  [gen] Set #%d '%s' — generating icon …", s.id, s.name)
            try:
                icon_b64 = generate_set_slot_icon(s.name, s.description)
                if not icon_b64:
                    logger.warning("    → generation returned None, skipping")
                    failed += 1
                    continue

                icon_bytes = base64.b64decode(icon_b64)
                set_icon_repo.upsert_icon(s.id, season_id, icon_bytes)
                generated += 1
                logger.info("    → stored (%d bytes)", len(icon_bytes))

                # Small delay to avoid hitting rate limits
                time.sleep(1)

            except Exception as exc:
                logger.error("    → FAILED: %s", exc, exc_info=True)
                failed += 1

    logger.info(
        "Done. total=%d  generated=%d  skipped=%d  failed=%d",
        total,
        generated,
        skipped,
        failed,
    )


if __name__ == "__main__":
    main()
