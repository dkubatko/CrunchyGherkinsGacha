"""
Tool to generate a poker card for a user.

Usage: python tools/generate_poker_card.py <username>

Example: python tools/generate_poker_card.py dkubatko

This will:
1. Look up the user by username in the database
2. Generate a fancy casino-style poker card using their profile image
3. Update the user's poker_cardb64 field in the database
4. Save the generated poker card image to data/output/
"""

import argparse
import base64
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

# Add parent directory to path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import connect, User
from utils.gemini import GeminiUtil

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables needed for GeminiUtil
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
IMAGE_GEN_MODEL = os.getenv("IMAGE_GEN_MODEL")


def find_user_by_username(username: str):
    """Find a user by username in the database."""
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?) AND profile_imageb64 IS NOT NULL",
            (username,),
        )
        row = cursor.fetchone()
        if row:
            return User(**row)
        return None
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


def generate_poker_card(username: str, output_dir: str):
    """
    Generate a poker card for a user.

    Args:
        username: Username of the user
        output_dir: Directory to save the output image

    Returns:
        Tuple of (output_path, success) or (None, False) on failure
    """
    # Find the user
    logger.info(f"Looking for user: {username}")
    user = find_user_by_username(username)

    if not user:
        logger.error(f"Could not find user with username: {username}")
        logger.info("Tip: Check the exact username in the database")
        return None, False

    logger.info(f"Found user: {user.username} (ID: {user.user_id})")

    if not user.profile_imageb64:
        logger.error(f"No profile image found for user: {username}")
        return None, False

    # Initialize Gemini utility
    logger.info(f"Generating poker card for user: {user.username}")
    gemini_util = GeminiUtil(GOOGLE_API_KEY, IMAGE_GEN_MODEL)

    # Generate the poker card
    try:
        poker_cardb64 = gemini_util.generate_poker_card(base_image_b64=user.profile_imageb64)

        if not poker_cardb64:
            logger.error("Poker card generation failed - no image returned")
            return None, False

        # Update the user's poker_cardb64 field in the database
        logger.info("Updating user's poker card in database...")
        success = update_user_poker_card(user.user_id, poker_cardb64)
        if success:
            logger.info(f"✅ User poker card updated in database")
        else:
            logger.warning(f"⚠️ Failed to update user poker card in database")
            return None, False

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Generate output filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_username = user.username.replace(" ", "_").replace("/", "_")
        filename = f"poker_card_{safe_username}_{timestamp}.png"
        output_path = os.path.join(output_dir, filename)

        # Decode and save the image
        image_bytes = base64.b64decode(poker_cardb64)
        with open(output_path, "wb") as f:
            f.write(image_bytes)

        logger.info(f"✅ Poker card image saved: {output_path}")
        return output_path, True

    except Exception as e:
        logger.error(f"Error generating poker card: {e}")
        return None, False


def main():
    parser = argparse.ArgumentParser(
        description="Generate a poker card for a user",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/generate_poker_card.py dkubatko
  python tools/generate_poker_card.py krypthos
        """,
    )

    parser.add_argument("username", help="Username of the user to generate poker card for")

    args = parser.parse_args()

    # Set output directory
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "output"
    )

    result, success = generate_poker_card(args.username, output_dir)

    if result and success:
        print(f"\n✅ Success!")
        print(f"   User: {args.username}")
        print(f"   Image saved to: {result}")
        print(f"   Database updated: poker_cardb64 field")
        sys.exit(0)
    else:
        print("\n❌ Failed to generate poker card. Check logs for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
