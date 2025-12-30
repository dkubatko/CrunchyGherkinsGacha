"""Generate icons for all achievements that are missing an icon.

Usage:
    python tools/backfill_achievement_icons.py
    python tools/backfill_achievement_icons.py --save-previews
    python tools/backfill_achievement_icons.py --dry-run

This script will:
1. Query all achievements in the database
2. Find achievements that don't have an icon (icon_b64 is NULL)
3. Generate icons for each missing one using Gemini AI
4. Update the database with the generated icons
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root is on sys.path for module imports
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

# Must import after dotenv loading
from utils.achievement_icon import generate_achievement_icon, save_icon_preview  # noqa: E402
from utils.services import (  # noqa: E402
    get_all_achievements,
    update_achievement_icon,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate icons for all achievements missing an icon."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List achievements that need icons without generating them",
    )
    parser.add_argument(
        "--save-previews",
        action="store_true",
        help="Save previews of generated icons to data/output/",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay in seconds between API calls (default: 2.0)",
    )

    args = parser.parse_args()

    # Get all achievements
    all_achievements = get_all_achievements()

    if not all_achievements:
        logger.info("No achievements found in the database.")
        return

    # Find achievements without icons
    missing_icons = [a for a in all_achievements if not a.icon_b64]

    if not missing_icons:
        logger.info("All %d achievements already have icons.", len(all_achievements))
        return

    logger.info(
        "Found %d achievements without icons (out of %d total):",
        len(missing_icons),
        len(all_achievements),
    )
    for achievement in missing_icons:
        logger.info("  - [%d] %s: %s", achievement.id, achievement.name, achievement.description)

    if args.dry_run:
        logger.info("Dry run complete. Use without --dry-run to generate icons.")
        return

    # Generate icons for each
    success_count = 0
    fail_count = 0

    for i, achievement in enumerate(missing_icons):
        if i > 0:
            logger.info("Waiting %.1f seconds before next generation...", args.delay)
            time.sleep(args.delay)

        logger.info(
            "Processing %d/%d: '%s'",
            i + 1,
            len(missing_icons),
            achievement.name,
        )

        icon_b64 = generate_achievement_icon(achievement.name, achievement.description)

        if icon_b64 is None:
            logger.error("Failed to generate icon for '%s'", achievement.name)
            fail_count += 1
            continue

        if args.save_previews:
            output_dir = PROJECT_ROOT / "data" / "output"
            save_icon_preview(icon_b64, achievement.name, output_dir)

        # Update in database
        result = update_achievement_icon(achievement.name, icon_b64)
        if result:
            logger.info("Updated icon for '%s' (id=%d)", achievement.name, result.id)
            success_count += 1
        else:
            logger.error("Failed to update icon in database for '%s'", achievement.name)
            fail_count += 1

    logger.info(
        "Complete: %d succeeded, %d failed out of %d total",
        success_count,
        fail_count,
        len(missing_icons),
    )


if __name__ == "__main__":
    main()
