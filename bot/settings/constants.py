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
SLOT_WIN_CHANCE = config["SLOT_WIN_CHANCE"]

IMAGE_GENERATOR_INSTRUCTION = """
Using the provided sketch as the general guidance for layout, generate collectible trading card, based on the character in the picture with the following description:
<{modification} {name}> and {rarity} rarity.

Due to the card rarity, border color should be in {color} gamut and "creativeness factor" should be {creativeness_factor} / 100.
Less the creativeness factor less intense the card design should be.

Character:
Use flashy, eye-catching 2D digital art style for the character. 
Always apply styling above to the photos before using, do NOT use original photos unprocessed.
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
Add card name "{modification} {name}" in the bottom field of the layout.
Do NOT add any additional description.
"""

SLOT_MACHINE_INSTRUCTION = """
Create a casino slot machine icon featuring the person's portrait.

- Use the person's face, neck, and shoulders from the image
- Keep facial features recognizable
- Apply casino/slot machine themed styling
- Make it look like a premium slot machine symbol with bold, eye-catching appearance
- Use rich, saturated colors typical of slot machines (golds, reds, blues, purples)
- High-impact visual style suitable for gambling/casino theme - no text or decorative elements
- Do NOT add any border to the icon
- Output MUST be exactly 1:1 square aspect ratio
"""

REACTION_IN_PROGRESS = "🤔"

COLLECTION_CAPTION = (
    "<b>{lock_icon} [{card_id}] {card_title}</b>\n"
    "Rarity: <b>{rarity}</b>\n\n"
    "<i>Showing {current_index}/{total_cards} owned by @{username}</i>"
)

CARD_CAPTION_BASE = "<b>[{card_id}] {card_title}</b>\nRarity: <b>{rarity}</b>"
CARD_STATUS_UNCLAIMED = "\n\n<i>Unclaimed</i>"
CARD_STATUS_CLAIMED = "\n\n<i>Claimed by @{username}</i>"
CARD_STATUS_LOCKED = "\n<i>Locked from re-rolling</i>"
CARD_STATUS_REROLLING = "\n\n<b>Rerolling...</b>"
CARD_STATUS_REROLLED = (
    "\n\n<i>Rerolled from <b>{original_rarity}</b> to <b>{downgraded_rarity}</b></i>"
)
CARD_STATUS_ATTEMPTED = "\n<i>Attempted by: {users}</i>"

RECYCLE_ALLOWED_RARITIES = {
    "common": "Common",
    "rare": "Rare",
    "epic": "Epic",
}

RECYCLE_UPGRADE_MAP = {
    "Common": "Rare",
    "Rare": "Epic",
    "Epic": "Legendary",
}

RECYCLE_BURN_COUNT = 3
RECYCLE_MINIMUM_REQUIRED = RECYCLE_BURN_COUNT

RECYCLE_USAGE_MESSAGE = "Usage: /recycle <rarity> where rarity is one of common, rare, epic. Burns 3 unlocked cards of <rarity> to get one guaranteed <rarity + 1> card."
RECYCLE_DM_RESTRICTED_MESSAGE = "Recycling is only available in the group chat."
RECYCLE_CONFIRM_MESSAGE = (
    "Burn {burn_count} unlocked <b>{rarity}</b> cards to generate 1 <b>{upgraded_rarity}</b> card?"
)
RECYCLE_INSUFFICIENT_CARDS_MESSAGE = (
    "You need at least {required} {rarity} cards in this chat to recycle."
)
RECYCLE_ALREADY_RUNNING_MESSAGE = "You already have a recycle in progress."
RECYCLE_NOT_YOURS_MESSAGE = "This recycle prompt isn't for you!"
RECYCLE_UNKNOWN_RARITY_MESSAGE = "Unknown rarity. Please choose one of common, rare, or epic."
RECYCLE_FAILURE_NOT_ENOUGH_CARDS = "Recycle failed: not enough unlocked cards remaining."
RECYCLE_FAILURE_NO_PROFILE = (
    "Recycle failed: no eligible profiles available to create an upgraded card.\n"
    "Your cards were not burned."
)
RECYCLE_FAILURE_IMAGE = (
    "Recycle failed: image generation is unavailable right now. Your cards were not burned."
)
RECYCLE_FAILURE_UNEXPECTED = "An unexpected error occurred while recycling cards. Try again later."
RECYCLE_RESULT_APPENDIX = "\n\nBurned cards:\n\n<b>{burned_block}</b>\n\n"
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

SLOTS_VICTORY_PENDING_MESSAGE = (
    "@{username} won a <b>{rarity} {display_name}</b> in slots!\n\nGenerating card..."
)

SLOTS_VICTORY_RESULT_MESSAGE = (
    "@{username} won a <b>{rarity} {display_name}</b> in slots!\n\n"
    "<b>[{card_id}] {modifier} {base_name}</b>\n"
    "Rarity: <b>{rarity}</b>"
)

SLOTS_VICTORY_FAILURE_MESSAGE = "@{username} won a {rarity} {display_name} in slots!\n\nCard generation failed. Please try again later."

SLOTS_VIEW_IN_APP_LABEL = "View in the app!"
