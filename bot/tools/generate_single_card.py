"""
Tool to generate a single card with specified parameters.

Usage: python tools/generate_single_card.py <character_name> <modifier> <rarity> [--assign <username>] [--set <set_name>]

Example: python tools/generate_single_card.py Daniel Test Epic
Example: python tools/generate_single_card.py Daniel Golden random --assign dkubatko
Example: python tools/generate_single_card.py Daniel random Epic --set Classic
Example: python tools/generate_single_card.py Daniel random random --set Anime
Example: python tools/generate_single_card.py "John Doe" "Ice Dragon" Legendary

This will:
1. Look up the character by name in the database
2. Generate a card using the specified modifier and rarity (or random values from DB)
3. Add the card to the database (optionally with a set assignment)
4. Save the generated card image to data/output/
5. Optionally assign the card to a user if --assign is specified

Note: Use quotes around names/modifiers with spaces. Both modifier and rarity can be set to "random".
When modifier is "random", --set is required to pick a random modifier from that set in the database.
"""

import argparse
import base64
import logging
import os
import random
import sys
from datetime import datetime

from dotenv import load_dotenv

# Add parent directory to path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.services import card_service, modifier_service, set_service, user_service
from utils.schemas import Character, User
from utils.session import get_session
from utils.models import CharacterModel, UserModel
from sqlalchemy import func
from utils.gemini import GeminiUtil
from utils.schemas import Modifier
from settings.constants import RARITIES

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables needed for GeminiUtil
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
IMAGE_GEN_MODEL = os.getenv("IMAGE_GEN_MODEL")


def load_random_modifier_from_set(set_name: str, rarity: str = None):
    """
    Load a random modifier from a set in the database.

    Args:
        set_name: Name of the set (e.g., 'Classic', 'Anime')
        rarity: Optional rarity to filter modifiers by. If None, picks from all rarities.

    Returns:
        A tuple of (modifier_name, set_id, modifier_db_id) or raises if not found.
    """
    set_id = set_service.get_set_id_by_name(set_name)
    if set_id is None:
        raise ValueError(f"Set '{set_name}' not found in database")

    mods = modifier_service.get_modifiers_by_set(set_id)

    if rarity:
        mods = [m for m in mods if m.rarity == rarity]

    if not mods:
        raise ValueError(
            f"No modifiers found in set '{set_name}'" + (f" for rarity {rarity}" if rarity else "")
        )

    chosen = random.choice(mods)
    logger.info(
        f"Randomly selected modifier '{chosen.name}' from set '{set_name}'"
        + (f" (rarity: {rarity})" if rarity else "")
    )
    return chosen.name, set_id, chosen.id


def find_character_by_name(character_name: str):
    """Find a character by name across ALL chats in the database."""
    with get_session() as session:
        char_orm = (
            session.query(CharacterModel)
            .filter(func.lower(CharacterModel.name) == func.lower(character_name))
            .first()
        )
        if char_orm:
            return Character.from_orm(char_orm)
        return None


def find_user_by_name(display_name: str):
    """Find a user by display name across ALL users in the database."""
    with get_session() as session:
        user_orm = (
            session.query(UserModel)
            .filter(
                func.lower(UserModel.display_name) == func.lower(display_name),
                UserModel.profile_imageb64.isnot(None),
            )
            .first()
        )
        if user_orm:
            return User.from_orm(user_orm)
        return None


def generate_single_card(
    source_name: str,
    modifier: str,
    rarity: str,
    output_dir: str,
    assign_username: str = None,
    set_name: str = None,
):
    """
    Generate a single card with specified parameters.

    Args:
        source_name: Name of the character or user to use as base
        modifier: The modifier to apply (e.g., "Test", "Golden", etc.) or "random" to pick from set
        rarity: The rarity tier (Common, Rare, Epic, Legendary, Unique) or "random" to pick randomly
        output_dir: Directory to save the output image
        assign_username: Optional username to assign the card to
        set_name: Optional set name — required when modifier is "random"

    Returns:
        Tuple of (output_path, card_id) or (None, None) on failure
    """
    # Handle random rarity selection
    if rarity.lower() == "random":
        rarity = random.choice(list(RARITIES.keys()))
        logger.info(f"Randomly selected rarity: {rarity}")

    # Handle random modifier selection from set in DB
    resolved_set_id = None
    resolved_modifier_id = None
    if modifier.lower() == "random":
        if not set_name:
            logger.error("Must specify --set when using 'random' as modifier")
            return None, None
        try:
            modifier, resolved_set_id, resolved_modifier_id = load_random_modifier_from_set(
                set_name, rarity
            )
        except Exception as e:
            logger.error(f"Failed to load random modifier from set '{set_name}': {e}")
            return None, None

    # Validate rarity
    if rarity not in RARITIES:
        logger.error(f"Invalid rarity: {rarity}. Must be one of {list(RARITIES.keys())}")
        return None, None

    # Try to find the source (character or user) across ALL chats
    logger.info(f"Looking for source: {source_name}")

    character = find_character_by_name(source_name)
    user = None
    chat_id = None
    source_type = None
    source_id = None

    if character:
        logger.info(
            f"Found character: {character.name} (ID: {character.id}, Chat: {character.chat_id})"
        )
        base_name = character.name
        image_b64 = character.imageb64
        chat_id = character.chat_id
        source_type = "character"
        source_id = character.id
    else:
        # Try to find as user
        user = find_user_by_name(source_name)
        if user:
            logger.info(f"Found user: {user.display_name} (ID: {user.user_id})")
            base_name = user.display_name
            image_b64 = user.profile_imageb64
            source_type = "user"
            source_id = user.user_id
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
        owner_user_id = user_service.get_user_id_by_username(assign_username)
        if not owner_user_id:
            logger.error(f"Could not find user with username: {assign_username}")
            logger.info("Tip: Check the exact username in the database")
            return None, None
        # Get the actual username from the database (in case of case differences)
        owner_username = user_service.get_username_for_user_id(owner_user_id)
        if not owner_username:
            owner_username = assign_username  # fallback to provided username
        logger.info(f"Found user to assign card to: {owner_username} (ID: {owner_user_id})")

        # Set chat_id to the user's most frequently used chat_id
        user_chat_id = user_service.get_most_frequent_chat_id_for_user(owner_user_id)
        if user_chat_id:
            chat_id = user_chat_id
            logger.info(f"Using user's most frequent chat_id: {chat_id}")
        else:
            logger.info("User has no existing cards, using source chat_id")

    # Resolve set_id from set_name if provided (before image generation so we can pass set context)
    set_id = resolved_set_id
    modifier_id = resolved_modifier_id
    tool_modifier_info: Modifier | None = None
    if set_name and set_id is None:
        set_id = set_service.get_set_id_by_name(set_name)
        if set_id is None:
            logger.warning(f"Set '{set_name}' not found in database, card will have no set")

    # Try to resolve modifier_id from DB if not already known
    if modifier_id is None and set_id is not None:
        db_mod = modifier_service.get_modifier_by_name_and_set(modifier, set_id)
        if db_mod is not None:
            modifier_id = db_mod.id
            logger.info(f"Resolved modifier '{modifier}' to DB ID: {modifier_id}")
    if modifier_id is None:
        # Try across all sets by name + rarity
        mod_schema = modifier_service.get_modifier_by_name_and_rarity(modifier, rarity)
        if mod_schema is not None:
            modifier_id = mod_schema.id
            if set_id is None:
                set_id = mod_schema.set_id
            logger.info(f"Resolved modifier '{modifier}' to DB ID: {modifier_id}")

    if set_id is not None:
        logger.info(f"Using set '{set_name}' (ID: {set_id})")
        tool_modifier_info = Modifier(
            id=modifier_id or 0,
            name=modifier,
            set_id=set_id,
            set_name=set_name,
        )

    # Initialize Gemini utility
    logger.info(f"Generating card: {rarity} {modifier} {base_name}")
    gemini_util = GeminiUtil(GOOGLE_API_KEY, IMAGE_GEN_MODEL)

    # Generate the card image
    try:
        generated_image_b64 = gemini_util.generate_image(
            base_name=base_name,
            modifier=modifier,
            rarity=rarity,
            base_image_b64=image_b64,
            modifier_info=tool_modifier_info,
        )

        if not generated_image_b64:
            logger.error("Image generation failed - no image returned")
            return None, None

        # Add the card to the database
        logger.info("Adding card to database...")
        card_id = card_service.add_card(
            base_name=base_name,
            modifier=modifier,
            rarity=rarity,
            image_b64=generated_image_b64,
            chat_id=chat_id,
            source_type=source_type,
            source_id=source_id,
            set_id=set_id,
            modifier_id=modifier_id,
        )
        logger.info(f"✅ Card added to database with ID: {card_id}")

        # If assign_username was provided, set the card owner
        if owner_user_id and owner_username:
            logger.info(f"Assigning card to user {owner_username} (ID: {owner_user_id})...")
            success = card_service.set_card_owner(
                card_id=card_id, owner=owner_username, user_id=owner_user_id
            )
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
  python tools/generate_single_card.py Daniel Test Epic
  python tools/generate_single_card.py Daniel Golden random --assign dkubatko
  python tools/generate_single_card.py Daniel random Epic --set Classic
  python tools/generate_single_card.py Daniel random random --set Anime
  python tools/generate_single_card.py "John Doe" "Ice Dragon" Legendary

Available rarities: {', '.join(RARITIES.keys())}

Use quotes around names/modifiers only if they contain spaces.
When using --set with modifier "random", a random modifier will be picked from that set in the DB.
The random modifier will be filtered by the specified rarity (unless rarity is also "random").
Set rarity to "random" to pick a random rarity tier.
        """,
    )

    parser.add_argument("character_name", help="Name of the character or user to use as base")
    parser.add_argument(
        "modifier",
        help="The modifier to apply (e.g., 'Test', 'Golden') or 'random' with --set",
    )
    parser.add_argument(
        "rarity", help="The rarity tier (Common, Rare, Epic, Legendary, Unique) or 'random'"
    )
    parser.add_argument("--assign", dest="assign_username", help="Username to assign the card to")
    parser.add_argument(
        "--set",
        dest="set_name",
        help="Set name to assign the card to and/or pick random modifier from (e.g., 'Classic', 'Anime')",
    )

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
        args.assign_username,
        args.set_name,
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
