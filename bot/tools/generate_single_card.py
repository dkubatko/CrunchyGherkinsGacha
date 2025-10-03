"""
Tool to generate a single card with specified parameters.

Usage: python tools/generate_single_card.py <character_name> <modifier> <rarity>

Example: python tools/generate_single_card.py krypthos "Test" Epic

This will:
1. Look up the character by name in the database
2. Generate a card using the specified modifier and rarity
3. Save the generated card image to data/output/
"""

import base64
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

# Add parent directory to path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import connect, Character, User
from utils.gemini import GeminiUtil
from settings.constants import RARITIES

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def find_character_by_name(character_name: str):
    """Find a character by name across ALL chats in the database."""
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM characters WHERE LOWER(name) = LOWER(?)", (character_name,))
        row = cursor.fetchone()
        if row:
            return Character(**row)
        return None
    finally:
        conn.close()


def find_user_by_name(display_name: str):
    """Find a user by display name across ALL users in the database."""
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE LOWER(display_name) = LOWER(?) AND profile_imageb64 IS NOT NULL",
            (display_name,),
        )
        row = cursor.fetchone()
        if row:
            return User(**row)
        return None
    finally:
        conn.close()


def generate_single_card(source_name: str, modifier: str, rarity: str, output_dir: str):
    """
    Generate a single card with specified parameters.

    Args:
        source_name: Name of the character or user to use as base
        modifier: The modifier to apply (e.g., "Test", "Golden", etc.)
        rarity: The rarity tier (Common, Rare, Epic, Legendary)
        output_dir: Directory to save the output image
    """
    # Validate rarity
    if rarity not in RARITIES:
        logger.error(f"Invalid rarity: {rarity}. Must be one of {list(RARITIES.keys())}")
        return None

    # Try to find the source (character or user) across ALL chats
    logger.info(f"Looking for source: {source_name}")

    character = find_character_by_name(source_name)
    user = None

    if character:
        logger.info(
            f"Found character: {character.name} (ID: {character.id}, Chat: {character.chat_id})"
        )
        base_name = character.name
        image_b64 = character.imageb64
    else:
        # Try to find as user
        user = find_user_by_name(source_name)
        if user:
            logger.info(f"Found user: {user.display_name} (ID: {user.user_id})")
            base_name = user.display_name
            image_b64 = user.profile_imageb64
        else:
            logger.error(f"Could not find character or user with name: {source_name}")
            logger.info("Tip: Check the exact spelling in the database")
            return None

    if not image_b64:
        logger.error(f"No image found for source: {source_name}")
        return None

    # Initialize Gemini utility
    logger.info(f"Generating card: {rarity} {modifier} {base_name}")
    gemini_util = GeminiUtil()

    # Generate the card image
    try:
        generated_image_b64 = gemini_util.generate_image(
            base_name=base_name, modifier=modifier, rarity=rarity, base_image_b64=image_b64
        )

        if not generated_image_b64:
            logger.error("Image generation failed - no image returned")
            return None

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Generate output filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = base_name.replace(" ", "_").replace("/", "_")
        safe_modifier = modifier.replace(" ", "_").replace("/", "_")
        filename = f"{safe_name}_{safe_modifier}_{rarity}_{timestamp}.png"
        output_path = os.path.join(output_dir, filename)

        # Decode and save the image
        image_bytes = base64.b64decode(generated_image_b64)
        with open(output_path, "wb") as f:
            f.write(image_bytes)

        logger.info(f"✅ Card generated successfully: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Error generating card: {e}")
        return None


def main():
    if len(sys.argv) != 4:
        print("Usage: python tools/generate_single_card.py <character_name> <modifier> <rarity>")
        print("\nExample: python tools/generate_single_card.py krypthos Test Epic")
        print(f"\nAvailable rarities: {', '.join(RARITIES.keys())}")
        sys.exit(1)

    source_name = sys.argv[1]
    modifier = sys.argv[2]
    rarity = sys.argv[3]

    # Set output directory
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "output"
    )

    result = generate_single_card(source_name, modifier, rarity, output_dir)

    if result:
        print(f"\n✅ Success! Card saved to: {result}")
        sys.exit(0)
    else:
        print("\n❌ Failed to generate card. Check logs for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
