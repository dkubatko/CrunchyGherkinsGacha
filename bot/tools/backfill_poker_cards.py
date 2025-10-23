"""Backfill poker cards for all users and characters without poker cards.

Usage:
    python tools/backfill_poker_cards.py [--debug]

Options:
    --debug    Save generated poker card images to data/output/ folder as PNG files
"""

from __future__ import annotations

import argparse
import base64
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root is on sys.path for module imports
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

from utils.database import connect, User, Character  # noqa: E402
from utils.gemini import GeminiUtil  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables needed for GeminiUtil
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
IMAGE_GEN_MODEL = os.getenv("IMAGE_GEN_MODEL")


def get_users_without_poker_cards():
    """Get all users that have profile images but no poker cards."""
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM users 
            WHERE profile_imageb64 IS NOT NULL 
            AND profile_imageb64 != ''
            AND (poker_cardb64 IS NULL OR poker_cardb64 = '')
            """
        )
        rows = cursor.fetchall()
        return [User(**row) for row in rows]
    finally:
        conn.close()


def get_characters_without_poker_cards():
    """Get all characters that have images but no poker cards."""
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM characters 
            WHERE imageb64 IS NOT NULL 
            AND imageb64 != ''
            AND (poker_cardb64 IS NULL OR poker_cardb64 = '')
            """
        )
        rows = cursor.fetchall()
        return [Character(**row) for row in rows]
    finally:
        conn.close()


def update_user_poker_card(user_id: int, poker_cardb64: str) -> bool:
    """Update the user's poker_cardb64 field in the database."""
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET poker_cardb64 = ? WHERE user_id = ?",
            (poker_cardb64, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating user poker card: {e}")
        return False
    finally:
        conn.close()


def update_character_poker_card(character_id: int, poker_cardb64: str) -> bool:
    """Update the character's poker_cardb64 field in the database."""
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE characters SET poker_cardb64 = ? WHERE id = ?",
            (poker_cardb64, character_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating character poker card: {e}")
        return False
    finally:
        conn.close()


def save_debug_image(poker_cardb64: str, name: str, entity_type: str, output_dir: Path):
    """Save poker card image to output directory for debugging."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = name.replace(" ", "_").replace("/", "_")
        filename = f"poker_card_{entity_type}_{safe_name}_{timestamp}.png"
        output_path = output_dir / filename

        image_bytes = base64.b64decode(poker_cardb64)
        with open(output_path, "wb") as f:
            f.write(image_bytes)

        logger.info(f"  💾 Debug image saved: {output_path}")
    except Exception as e:
        logger.error(f"  ❌ Failed to save debug image: {e}")


def backfill_poker_cards(debug: bool = False):
    """Backfill poker cards for all users and characters without them."""
    # Initialize Gemini utility
    gemini_util = GeminiUtil(GOOGLE_API_KEY, IMAGE_GEN_MODEL)

    # Setup debug output directory if needed
    output_dir = None
    if debug:
        output_dir = PROJECT_ROOT / "data" / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Debug mode: saving images to {output_dir}")

    # Process users
    users = get_users_without_poker_cards()
    logger.info(f"Found {len(users)} users without poker cards")

    users_success = 0
    users_failed = 0
    users_skipped = 0

    for user in users:
        # Skip users without profile images
        if not user.profile_imageb64 or user.profile_imageb64.strip() == "":
            logger.info(
                f"⏭️  Skipping user: {user.username} (ID: {user.user_id}) - no profile image"
            )
            users_skipped += 1
            continue

        # Validate base64 image data
        try:
            base64.b64decode(user.profile_imageb64)
        except Exception as e:
            logger.error(
                f"⏭️  Skipping user: {user.username} (ID: {user.user_id}) - invalid base64 image: {e}"
            )
            users_skipped += 1
            continue

        print(f"Processing user: {user.username} (ID: {user.user_id})")
        try:
            poker_cardb64 = gemini_util.generate_poker_card(base_image_b64=user.profile_imageb64)

            if not poker_cardb64:
                print(f"  ❌ Failed to generate poker card for user: {user.username}")
                users_failed += 1
                continue

            print(f"  ✨ Generated poker card for user: {user.username}")

            # Update database
            success = update_user_poker_card(user.user_id, poker_cardb64)
            if success:
                print(f"  ✅ Poker card generated and saved to database")
                users_success += 1

                # Save debug image if requested
                if debug and output_dir:
                    save_debug_image(poker_cardb64, user.username, "user", output_dir)
            else:
                print(f"  ❌ Failed to update database for user: {user.username}")
                users_failed += 1

        except Exception as e:
            print(f"  ❌ Error processing user {user.username}: {e}")
            users_failed += 1

    # Process characters
    characters = get_characters_without_poker_cards()
    logger.info(f"\nFound {len(characters)} characters without poker cards")

    characters_success = 0
    characters_failed = 0
    characters_skipped = 0

    for character in characters:
        # Skip characters without images
        if not character.imageb64 or character.imageb64.strip() == "":
            logger.info(f"⏭️  Skipping character: {character.name} (ID: {character.id}) - no image")
            characters_skipped += 1
            continue

        # Validate base64 image data
        try:
            base64.b64decode(character.imageb64)
        except Exception as e:
            logger.error(
                f"⏭️  Skipping character: {character.name} (ID: {character.id}) - invalid base64 image: {e}"
            )
            characters_skipped += 1
            continue

        print(f"Processing character: {character.name} (ID: {character.id})")
        try:
            poker_cardb64 = gemini_util.generate_poker_card(base_image_b64=character.imageb64)

            if not poker_cardb64:
                print(f"  ❌ Failed to generate poker card for character: {character.name}")
                characters_failed += 1
                continue

            print(f"  ✨ Generated poker card for character: {character.name}")

            # Update database
            success = update_character_poker_card(character.id, poker_cardb64)
            if success:
                print(f"  ✅ Poker card generated and saved to database")
                characters_success += 1

                # Save debug image if requested
                if debug and output_dir:
                    save_debug_image(poker_cardb64, character.name, "character", output_dir)
            else:
                print(f"  ❌ Failed to update database for character: {character.name}")
                characters_failed += 1

        except Exception as e:
            print(f"  ❌ Error processing character {character.name}: {e}")
            characters_failed += 1

    # Summary
    print("\n" + "=" * 60)
    print("BACKFILL SUMMARY")
    print("=" * 60)
    print(f"Users:")
    print(f"  ✅ Success: {users_success}")
    print(f"  ❌ Failed:  {users_failed}")
    print(f"  ⏭️  Skipped: {users_skipped} (no profile image)")
    print(f"\nCharacters:")
    print(f"  ✅ Success: {characters_success}")
    print(f"  ❌ Failed:  {characters_failed}")
    print(f"  ⏭️  Skipped: {characters_skipped} (no image)")
    print(f"\nTotal:")
    print(f"  ✅ Success: {users_success + characters_success}")
    print(f"  ❌ Failed:  {users_failed + characters_failed}")
    print(f"  ⏭️  Skipped: {users_skipped + characters_skipped}")
    if debug:
        print(f"\n💾 Debug images saved to: {output_dir}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Backfill poker cards for all users and characters without them",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/backfill_poker_cards.py
  python tools/backfill_poker_cards.py --debug
        """,
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save generated poker card images to data/output/ folder as PNG files",
    )

    args = parser.parse_args()

    try:
        backfill_poker_cards(debug=args.debug)
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
