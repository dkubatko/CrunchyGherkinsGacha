"""
Tool to generate a single card with specified parameters.

Usage: python tools/generate_single_card.py <character_name> <modifier> <rarity> [--assign <username>]

Example: python tools/generate_single_card.py krypthos "Test" Epic
Example: python tools/generate_single_card.py krypthos "Test" Epic --assign dkubatko

This will:
1. Look up the character by name in the database
2. Generate a card using the specified modifier and rarity
3. Add the card to the database
4. Save the generated card image to data/output/
5. Optionally assign the card to a user if --assign is specified
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

from utils.database import connect, Character, User, add_card, get_user_id_by_username, get_username_for_user_id, set_card_owner
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


def generate_single_card(source_name: str, modifier: str, rarity: str, output_dir: str, assign_username: str = None):
    """
    Generate a single card with specified parameters.

    Args:
        source_name: Name of the character or user to use as base
        modifier: The modifier to apply (e.g., "Test", "Golden", etc.)
        rarity: The rarity tier (Common, Rare, Epic, Legendary)
        output_dir: Directory to save the output image
        assign_username: Optional username to assign the card to

    Returns:
        Tuple of (output_path, card_id) or (None, None) on failure
    """
    # Validate rarity
    if rarity not in RARITIES:
        logger.error(f"Invalid rarity: {rarity}. Must be one of {list(RARITIES.keys())}")
        return None, None

    # Try to find the source (character or user) across ALL chats
    logger.info(f"Looking for source: {source_name}")

    character = find_character_by_name(source_name)
    user = None
    chat_id = None

    if character:
        logger.info(
            f"Found character: {character.name} (ID: {character.id}, Chat: {character.chat_id})"
        )
        base_name = character.name
        image_b64 = character.imageb64
        chat_id = character.chat_id
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
            return None, None

    if not image_b64:
        logger.error(f"No image found for source: {source_name}")
        return None, None

    # Resolve assign_username to user_id if provided
    owner_user_id = None
    owner_username = None
    if assign_username:
        owner_user_id = get_user_id_by_username(assign_username)
        if not owner_user_id:
            logger.error(f"Could not find user with username: {assign_username}")
            logger.info("Tip: Check the exact username in the database")
            return None, None
        # Get the actual username from the database (in case of case differences)
        owner_username = get_username_for_user_id(owner_user_id)
        if not owner_username:
            owner_username = assign_username  # fallback to provided username
        logger.info(f"Found user to assign card to: {owner_username} (ID: {owner_user_id})")

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
            return None, None

        # Add the card to the database
        logger.info("Adding card to database...")
        card_id = add_card(
            base_name=base_name,
            modifier=modifier,
            rarity=rarity,
            image_b64=generated_image_b64,
            chat_id=chat_id
        )
        logger.info(f"✅ Card added to database with ID: {card_id}")

        # If assign_username was provided, set the card owner
        if owner_user_id and owner_username:
            logger.info(f"Assigning card to user {owner_username} (ID: {owner_user_id})...")
            success = set_card_owner(card_id=card_id, owner=owner_username, user_id=owner_user_id)
            if success:
                logger.info(f"✅ Card ownership set successfully")
            else:
                logger.warning(f"⚠️ Failed to set card ownership")

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

        logger.info(f"✅ Card image saved: {output_path}")
        return output_path, card_id

    except Exception as e:
        logger.error(f"Error generating card: {e}")
        return None, None


def main():
    parser = argparse.ArgumentParser(
        description="Generate a single card with specified parameters",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python tools/generate_single_card.py krypthos "Test" Epic
  python tools/generate_single_card.py krypthos "Test" Epic --assign dkubatko

Available rarities: {', '.join(RARITIES.keys())}
        """
    )
    
    parser.add_argument("character_name", help="Name of the character or user to use as base")
    parser.add_argument("modifier", help="The modifier to apply (e.g., 'Test', 'Golden', etc.)")
    parser.add_argument("rarity", help="The rarity tier (Common, Rare, Epic, Legendary)")
    parser.add_argument("--assign", dest="assign_username", help="Username to assign the card to")
    
    args = parser.parse_args()

    # Set output directory
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "output"
    )

    result, card_id = generate_single_card(
        args.character_name, 
        args.modifier, 
        args.rarity, 
        output_dir,
        args.assign_username
    )

    if result and card_id:
        print(f"\n✅ Success!")
        print(f"   Card ID: {card_id}")
        print(f"   Image saved to: {result}")
        if args.assign_username:
            print(f"   Assigned to: {args.assign_username}")
        sys.exit(0)
    else:
        print("\n❌ Failed to generate card. Check logs for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
