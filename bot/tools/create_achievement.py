"""Generate and register an achievement with an AI-generated icon.

Usage:
    python tools/create_achievement.py --name "Spinner" --description "Spend 100 spins"
    python tools/create_achievement.py --name "Roller" --description "Roll 50 cards" --update-icon

This script will:
1. Generate a circular achievement badge icon using Gemini AI
2. Resize it to 256x256 pixels
3. Register or update the achievement in the database
"""

from __future__ import annotations

import argparse
import logging
import sys
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
    get_achievement_by_name,
    register_achievement,
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
        description="Generate and register an achievement with an AI-generated icon."
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Unique name for the achievement",
    )
    parser.add_argument(
        "--description",
        required=True,
        help="Human-readable description of how to earn the achievement",
    )
    parser.add_argument(
        "--update-icon",
        action="store_true",
        help="Update the icon even if the achievement already exists",
    )
    parser.add_argument(
        "--no-generate",
        action="store_true",
        help="Register without generating an icon (icon can be added later)",
    )
    parser.add_argument(
        "--save-preview",
        action="store_true",
        help="Save a preview of the generated icon to data/output/",
    )

    args = parser.parse_args()

    # Check if achievement already exists
    existing = get_achievement_by_name(args.name)

    if existing and not args.update_icon:
        logger.info(
            "Achievement '%s' already exists (id=%d). Use --update-icon to regenerate the icon.",
            args.name,
            existing.id,
        )
        return

    # Generate icon unless --no-generate is specified
    icon_b64 = None
    if not args.no_generate:
        icon_b64 = generate_achievement_icon(args.name, args.description)
        if icon_b64 is None:
            logger.error("Failed to generate icon. Aborting.")
            sys.exit(1)

        if args.save_preview:
            output_dir = PROJECT_ROOT / "data" / "output"
            save_icon_preview(icon_b64, args.name, output_dir)

    # Register or update achievement
    if existing:
        if icon_b64:
            result = update_achievement_icon(args.name, icon_b64)
            if result:
                logger.info("Updated icon for achievement '%s' (id=%d)", args.name, result.id)
            else:
                logger.error("Failed to update achievement icon")
                sys.exit(1)
    else:
        result = register_achievement(args.name, args.description, icon_b64)
        logger.info(
            "Registered achievement '%s' (id=%d)%s",
            args.name,
            result.id,
            " with icon" if icon_b64 else " without icon",
        )


if __name__ == "__main__":
    main()
