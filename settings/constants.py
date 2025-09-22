import json
import os

# Load configuration from config.json
_config = None


def load_config():
    global _config
    if _config is None:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            _config = json.load(f)
    return _config


# Load configuration
config = load_config()
RARITIES = config["RARITIES"]
DB_PATH = config["DB_PATH"]
BASE_IMAGE_PATH = config["BASE_IMAGE_PATH"]
CARD_TEMPLATES_PATH = config["CARD_TEMPLATES_PATH"]

IMAGE_GENERATOR_INSTRUCTION = """
Using the provided sketch as the general guidance for layout, generate collectible trading card, based on the character in the picture with the following description:
<{modification} {name}> and {rarity} rarity.

Due to the card rarity, border color should be in {color} gamut and "creativeness factor" should be {creativeness_factor} / 100.
Less the creativeness factor less intense the card design should be.

Character:
Use flashy, eye-catching 2D digital art style for the character. 
Always apply styling to the photos before using, no photorealistic images.
Keep the face of the character consistent with their image, character must be recognizable.
Modify the character image to reflect the card name. 

Card Layout:
Aspect ratio MUST be 9:16. 
Only use the provided card layout sketch as a reference. Add layout modifications based on the card name and creativeness factor.
Do NOT use the reference layout directly, make significant style modifications.
Card should take up the entire image space, full width and full height, edge-to-edge. 
ABSOLUTELY NO blank/empty/white space around the card.

Text:
Do NOT include rarity information on the card.
Do NOT include any text other than the card name on the card.
Add card name "{modification} {name}" to the bottom field, no description.
"""

REACTION_IN_PROGRESS = "🤔"

COLLECTION_CAPTION = (
    "<b>[{card_id}] {card_title}</b>\n"
    "Rarity: <b>{rarity}</b>\n\n"
    "<i>Showing {current_index}/{total_cards} owned by @{username}</i>"
)

CARD_CAPTION_BASE = "<b>[{card_id}] {card_title}</b>\nRarity: <b>{rarity}</b>"
CARD_STATUS_UNCLAIMED = "\n\n<i>Unclaimed</i>"
CARD_STATUS_CLAIMED = "\n\n<i>Claimed by @{username}</i>"
CARD_STATUS_REROLLING = "<b>Rerolling...</b>"
CARD_STATUS_REROLLED = (
    "\n\n<i>Rerolled from <b>{original_rarity}</b> to <b>{downgraded_rarity}</b></i>"
)
CARD_STATUS_ATTEMPTED = "\n<i>Attempted by: {users}</i>"

TRADE_REQUEST_MESSAGE = (
    "Trade requested:\n\n"
    "@{user1_username}'s\n<b>{card1_title}</b>\n\n"
    "🔄\n\n"
    "@{user2_username}'s\n<b>{card2_title}</b>"
)

TRADE_COMPLETE_MESSAGE = (
    "Trade completed:\n\n"
    "@{user1_username}'s\n<b>{card1_title}</b>\n\n"
    "🤝\n\n"
    "@{user2_username}'s\n<b>{card2_title}</b>"
)

TRADE_REJECTED_MESSAGE = (
    "Trade rejected:\n\n"
    "@{user1_username}'s\n<b>{card1_title}</b>\n\n"
    "🚫\n\n"
    "@{user2_username}'s\n<b>{card2_title}</b>"
)
