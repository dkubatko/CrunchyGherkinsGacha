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
CURRENT_SEASON = config.get("CURRENT_SEASON", 0)
SLOT_WIN_CHANCE = config["SLOT_WIN_CHANCE"]
SLOT_CLAIM_CHANCE = config["SLOT_CLAIM_CHANCE"]
MINESWEEPER_MINE_COUNT = config.get("MINESWEEPER_MINE_COUNT", 2)
MINESWEEPER_CLAIM_POINT_COUNT = config.get("MINESWEEPER_CLAIM_POINT_COUNT", 1)
GEMINI_TIMEOUT_SECONDS = config.get("GEMINI_TIMEOUT_SECONDS", 180)

# RTB (Ride the Bus) constants
RTB_MIN_BET = config.get("RTB_MIN_BET", 10)
RTB_MAX_BET = config.get("RTB_MAX_BET", 50)
RTB_CARDS_PER_GAME = config.get("RTB_CARDS_PER_GAME", 5)
RTB_NUM_CARDS_TO_UNLOCK = config.get("RTB_NUM_CARDS_TO_UNLOCK", 100)
_rtb_mult = config.get("RTB_MULTIPLIER_PROGRESSION", {"1": 1, "2": 2, "3": 3, "4": 5, "5": 10})
RTB_MULTIPLIER_PROGRESSION = {int(k): v for k, v in _rtb_mult.items()}
# Cooldown in seconds after winning or cashing out (30 min production, 1 min debug)
RTB_COOLDOWN_SECONDS = config.get("RTB_COOLDOWN_SECONDS", 30 * 60)
RTB_DEBUG_COOLDOWN_SECONDS = config.get("RTB_DEBUG_COOLDOWN_SECONDS", 30)

# Rarity order derived from RARITIES keys (ordered in config.json)
RARITY_ORDER = list(RARITIES.keys())


DEFAULT_LOCK_COST = 1
DEFAULT_CLAIM_COST = 1
DEFAULT_SPIN_REWARD = 0


def get_lock_cost(rarity: str) -> int:
    """Return the configured lock cost for the provided rarity."""
    rarity_config = config.get("RARITIES", {}).get(rarity, {})
    raw_cost = rarity_config.get("lock_cost", DEFAULT_LOCK_COST)

    try:
        cost = int(raw_cost)
    except (TypeError, ValueError):
        return DEFAULT_LOCK_COST

    return max(cost, 1)


def get_claim_cost(rarity: str) -> int:
    """Return the configured claim cost for the provided rarity."""
    rarity_config = config.get("RARITIES", {}).get(rarity, {})
    raw_cost = rarity_config.get("claim_cost", DEFAULT_CLAIM_COST)

    try:
        cost = int(raw_cost)
    except (TypeError, ValueError):
        return DEFAULT_CLAIM_COST

    return max(cost, 1)


def get_spin_reward(rarity: str) -> int:
    """Return the configured spin reward for the provided rarity."""
    rarity_config = config.get("RARITIES", {}).get(rarity, {})
    raw_reward = rarity_config.get("spin_reward", DEFAULT_SPIN_REWARD)

    try:
        reward = int(raw_reward)
    except (TypeError, ValueError):
        return DEFAULT_SPIN_REWARD

    return max(reward, 0)


def get_refresh_cost(rarity: str) -> int:
    """Get the refresh cost for a given rarity."""
    return config.get("RARITIES", {}).get(rarity, {}).get("refresh_cost", 5)


def _build_cost_summary(cost_lookup) -> str:
    parts = []
    for rarity_name in RARITIES.keys():
        cost = cost_lookup(rarity_name)
        initial = rarity_name[:1].upper()
        parts.append(f"{initial}: {cost}")
    return ", ".join(parts)


LOCK_COST_SUMMARY = _build_cost_summary(get_lock_cost)
REFRESH_COST_SUMMARY = _build_cost_summary(get_refresh_cost)


IMAGE_GENERATOR_INSTRUCTION = """
**Generate a 5:7 aspect ratio detailed collectible trading card using the provided template image as layout reference, and the character image as the subject of the illustration.**

**--- Guiding Principles ---**
You must achieve the following goals:
1.  **Thematic Transformation:** The card must be a creative visual representation reflective of its name, "{modification} {name}", where {modification} is the modification tag and {name} is the character's name.
2.  **Character Recognition:** The person or character depicted on the card must remain clearly and unmistakably recognizable from the input photo.

**1. Art Style & Theme:**
The overall style should be a high-quality, detailed digital illustration.
   - **Literal Interpretation:** The visual theme and art style MUST be a direct interpretation of the `{modification}` modification tag.{set_context}
   - **AVOID THEME DEFAULTS:** You are strictly forbidden from defaulting to a generic theme (for example **fantasy, magic, arcane, sci-fi, or futuristic**) unless the tag requests that theme explicitly.
   - **Current-Day Grounding:** If modification tag `{modification}` is an abstract concept, a personality trait, or a term without an obvious visual theme, your interpretation MUST be grounded in a **contemporary, real-world, non-speculative context**.

**2. Card Transformation & Layout:**
   - **Main Artwork:** the main area of the template should contain the character and a richly detailed, themed background. This artwork must fill the entire area within the border of the card.
   - **Layering:** The styled nameplate must be a standalone, opaque "floating" piece layered on top of the main artwork, **disconnected** from the border of the card.
   - **Final Frame:** The final image **must retain the exact edge-to-edge dimensions of the provided template**, with no added external padding, margins, or borders.

**3. Character Likeness & Modification:**
   - **Fusion Concept:** Create a visual *hybrid* that blends the reference person with the concept specified by the `{modification}` tag.
   - **Recognizability Anchor:** The character's **unique identifying facial features**, and reference character overall must remain recognizable.
   - **Art Style** Stylize & render the character in the specified art style & theme. Do NOT re-use or lightly filter the original photo.
   - **Artistic Mandate:** Push the thematic interpretation to its most evocative and visually striking form that remains **permissible by content policy**. Maximize suggestive elements while ensuring that the image is successfully generated.

**4. Card Border Styling:**
   - **Thematic Elements:** The card border is a key thematic element and **MUST** be styled with details that match the theme. That may include patterns, textures, depth, and any other effects.
   - **Edge Placement:** The border **MUST** be positioned EXACTLY around the edge of the card, flush with the outer perimeter of the image. The border **must NOT** be isolated or floating within the card interior.
   - **Size Constraint:** The border should take no more than 10% of the total card area (measured from the edge inward).
   - **Always Apply Styling:** The border **MUST** always have thematic styling applied. *NEVER* leave a plain, solid color border/outline around the generated card.

**5. Nameplate & Text Styling:**
   - **Thematic Elements:** The nameplate and card title within are key thematic elements and **MUST** be styled consistently with the rest of the generated card. Do NOT use plain or generic styling for the nameplate and text.
   - **Styling:** The nameplate border, background, text and font must incorporate design elements (e.g., depth, patterns, textures, lighting) that reflect the card's theme, and be consistent with the styling of the card border.
   - **Size Constraint:** The nameplate should take no more than 15% of the total card area.
   - **Placement:** The card name "{modification} {name}" MUST be placed horizontally, centered and contained within the nameplate, while **fitting in one line** if possible.
   - **Other text:** **DO NOT** include any other text anywhere on the card.

**6. Rarity Color Application:**
   - The card's border and nameplate **MUST** use a {color} color palette to indicate card's rarity.
   - This color restriction applies **ONLY to the border and the nameplate**.
   - The main artwork, background, and character are **NOT constrained** by this color and should use any colors that best represent the theme.

**7. Creativity Factor: {creativeness_factor}/100**
   - The "creativity factor" dictates the **visual complexity** of the card's design, including the styling complexity for the border, nameplate, and text.
     Higher creativity factor allows to go beyond the theme basics and create complex and sophisticated design based on the specified tag & overall theme.
     Creativity factor does **NOT** control the art style genre or the degree of deviation from the person's likeness.
     - **Low creativity (e.g., 10/100):** A simple, clean design with minor details and effects, while following the general card theme directly.
     - **Medium creativity (e.g., 50/100):** A detailed design with balanced thematic patterns, complex effects, and noticeable but not overwhelming decorative elements throughout the card's design.
     - **High creativity (e.g., 90/100):** Deep exploration of the theme with thoughtful and intricate design work throughout the card: high level of detail, sophisticated design, dynamic lighting, depth, convexity, and other complex thematic effects & elements. 
"""

UNIQUE_ADDENDUM = """
**8. Unique Card Requirements:**
   - This is a "Unique" rarity card, which means it is a one-of-a-kind creation and is of higher rarity than any other.
   - The design must be absolutely mind-blowing in quality, detail, and thematic execution.
   - Push the boundaries of the art style and theme to the maximum extent possible.
   - Ensure the character remains recognizable, but integrated into a spectacular scene or composition.
   - **Color Freedom:** You are NOT bound by a specific rarity color. Choose ANY color palette for the border and nameplate that best enhances the card's theme and visual impact.
"""

SET_CONTEXT = """\n   - The card is part of a themed set {set_details}. The modification tag should be interpreted within the context of that general theme; set should not influence the card directly, but rather provide the interpretive context for the modification tag."""

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
    "<b>{lock_icon}[{card_id}] {card_title}</b>\n"
    "Rarity: <b>{rarity}</b>\n"
    "Set: <b>{set_name}</b>\n\n"
    "<i>Showing {current_index}/{total_cards} owned by @{username}</i>"
)

CARD_CAPTION_BASE = (
    "<b>[{card_id}] {card_title}</b>\nRarity: <b>{rarity}</b>\nSet: <b>{set_name}</b>"
)
CARD_STATUS_UNCLAIMED = "\n\n<i>Unclaimed</i>"
CARD_STATUS_CLAIMED = "\n\n<i>Claimed by @{username}</i>"
CARD_STATUS_LOCKED = "\n\n<i>Locked from re-rolling</i>"
CARD_STATUS_REROLLING = "\n\n<b>Rerolling...</b>"
CARD_STATUS_REROLLED = (
    "\n\n<i>Rerolled from <b>{original_rarity}</b> to <b>{downgraded_rarity}</b></i>"
)
CARD_STATUS_ATTEMPTED = "\n<i>Attempted by: {users}</i>"
CARD_STATUS_PRE_CLAIM_MESSAGES = [
    "Materializing the card...",
    "Glueing the paper...",
    "Adding shine...",
    "Sprinkling glitter...",
    "Polishing edges...",
    "Infusing the colors...",
    "Consulting the oracle...",
    "Rolling the dice...",
    "Summoning energy...",
    "Charging crystals...",
    "Taunting the players...",
    "Warming up dinner...",
    "Getting unstuck...",
    "Messing around...",
    "Finding inspiration...",
    "Doubting existence...",
    "Almost ready...",
    "Just a moment...",
]
PRE_CLAIM_ROTATION_INTERVAL = config.get(
    "PRE_CLAIM_ROTATION_INTERVAL", 1.5
)  # Seconds between message rotations

# Claim unlock delay configuration (random delay in seconds)
CLAIM_UNLOCK_DELAY_LOW = config.get("CLAIM_UNLOCK_DELAY_LOW", 3)  # Minimum delay in seconds
CLAIM_UNLOCK_DELAY_HIGH = config.get("CLAIM_UNLOCK_DELAY_HIGH", 6)  # Maximum delay in seconds

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

DEFAULT_RECYCLE_COST = 3


def get_recycle_required_cards(rarity_name: str) -> int:
    """Return how many cards must be burned to upgrade the given rarity.

    The burn requirement for a rarity is determined by the recycle_cost of the
    next rarity in the progression (rarity + 1).
    """

    upgrade_rarity = RECYCLE_UPGRADE_MAP.get(rarity_name)
    if not upgrade_rarity:
        return DEFAULT_RECYCLE_COST

    upgrade_config = RARITIES.get(upgrade_rarity, {})
    required = upgrade_config.get("recycle_cost", DEFAULT_RECYCLE_COST)

    try:
        required_int = int(required)
    except (TypeError, ValueError):
        return DEFAULT_RECYCLE_COST

    return max(required_int, 3)


RECYCLE_USAGE_MESSAGE = (
    "Usage: /recycle <rarity> where rarity is one of common, rare, epic.\n"
    "Burns unlocked cards of that rarity to guarantee the next tier.\n\n"
    "3C -> 1R\n3R -> 1E\n4E -> 1L"
)
RECYCLE_DM_RESTRICTED_MESSAGE = "Recycling is only available in the group chat."
RECYCLE_SELECT_RARITY_MESSAGE = "Select <b>card rarity</b> to recycle"
RECYCLE_CONFIRM_MESSAGE = (
    "Burn {burn_count} unlocked <b>{rarity}</b> cards to generate 1 <b>{upgraded_rarity}</b> card?"
)
RECYCLE_INSUFFICIENT_CARDS_MESSAGE = (
    "You need at least {required} unlocked {rarity} cards in this chat to recycle."
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

BURN_USAGE_MESSAGE = "Usage: /burn <card_id>. Burns a card you own in this chat for spins."
BURN_DM_RESTRICTED_MESSAGE = "Burning cards is only available in the group chat."
BURN_INVALID_ID_MESSAGE = "Invalid card ID. Please provide a numeric card ID."
BURN_CARD_NOT_FOUND_MESSAGE = "Card not found. Check the ID and try again."
BURN_NOT_YOURS_MESSAGE = "You can only burn cards you currently own."
BURN_CHAT_MISMATCH_MESSAGE = "This card doesn't belong to this chat."
BURN_CONFIRM_MESSAGE = (
    "Burn <b>[{card_id}] {rarity} {card_title}</b> for <b>{spin_reward} spins</b>?"
)
BURN_CANCELLED_MESSAGE = "Burn cancelled."
BURN_ALREADY_RUNNING_MESSAGE = "You already have a burn in progress."
BURN_PROCESSING_MESSAGE = "Burning card..."
BURN_FAILURE_MESSAGE = "Burn failed. Please try again later."
BURN_FAILURE_SPINS_MESSAGE = "Card burned but awarding spins failed. Please contact an admin."
BURN_SUCCESS_MESSAGE = (
    "Burn complete! Awarded <b>{spin_reward} spins</b>.\n"
    "New spin balance: <b>{new_spin_total}</b>."
)

CREATE_USAGE_MESSAGE = "Usage: /create &lt;Modifier&gt; &lt;Name&gt;\n[optional description]\n\nCreates a <b>Unique</b> card by burning {cost} Legendary cards.\n\nYou can add a description (up to 300 characters) on a new line to guide the art."
CREATE_DM_RESTRICTED_MESSAGE = "Creating unique cards is only available in the group chat."
CREATE_CONFIRM_MESSAGE = "Burn {cost} unlocked <b>Legendary</b> cards to create <b>Unique</b> card <b>{modifier} {name}</b>?"
CREATE_WARNING_EXISTING_MODIFIER = (
    "\n\n⚠️ <b>Warning:</b> The modifier '<b>{modifier}</b>' has already been used in this chat."
)
CREATE_DUPLICATE_UNIQUE_MODIFIER_MESSAGE = (
    "Modifier '<b>{modifier}</b>' has already been used for another Unique card in this chat. "
    "Please choose a different modifier."
)
CREATE_INSUFFICIENT_CARDS_MESSAGE = (
    "You need at least {required} unlocked Legendary cards in this chat to create a Unique card."
)
CREATE_ALREADY_RUNNING_MESSAGE = "You already have a creation in progress."
CREATE_NOT_YOURS_MESSAGE = "This creation prompt isn't for you!"
CREATE_FAILURE_NO_PROFILE = "Creation failed: could not find a profile for '{name}'."
CREATE_FAILURE_IMAGE = (
    "Creation failed: image generation is unavailable right now. Your cards were not burned."
)
CREATE_FAILURE_UNEXPECTED = "An unexpected error occurred while creating the card. Try again later."
CREATE_SUCCESS_MESSAGE = "Successfully created <b>Unique</b> card <b>{card_title}</b>!"
CREATE_CANCELLED_MESSAGE = "Creation cancelled."
CREATE_PROCESSING_MESSAGE = "Creating <b>Unique</b> card..."

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

TRADE_CANCELLED_MESSAGE = (
    "Trade cancelled:\n\n"
    "@{user1_username}'s\n<b>{card1_title}</b>\n\n"
    "❌\n\n"
    "@{user2_username}'s\n<b>{card2_title}</b>"
)

SLOTS_VICTORY_PENDING_MESSAGE = (
    "@{username} won a <b>{rarity} {display_name}</b> in slots!\n\nGenerating card..."
)

SLOTS_VICTORY_RESULT_MESSAGE = (
    "@{username} won a <b>{rarity} {display_name}</b> in slots!\n\n"
    "<b>[{card_id}] {modifier} {base_name}</b>\n"
    "Rarity: <b>{rarity}</b>\n"
    "Set: <b>{set_name}</b>"
)

SLOTS_VICTORY_FAILURE_MESSAGE = (
    "@{username} won a {rarity} {display_name} in slots!\n\nCard generation failed."
)

MEGASPIN_VICTORY_PENDING_MESSAGE = "@{username} used a <b>megaspin</b> and won a <b>{rarity} {display_name}</b>!\n\nGenerating card..."

MEGASPIN_VICTORY_RESULT_MESSAGE = (
    "@{username} used a <b>megaspin</b> and won a <b>{rarity} {display_name}</b>!\n\n"
    "<b>[{card_id}] {modifier} {base_name}</b>\n"
    "Rarity: <b>{rarity}</b>\n"
    "Set: <b>{set_name}</b>"
)

MEGASPIN_VICTORY_FAILURE_MESSAGE = "@{username} used a <b>megaspin</b> and won a {rarity} {display_name}!\n\nCard generation failed."

SLOTS_VIEW_IN_APP_LABEL = "View in the app!"

SLOTS_VICTORY_REFUND_MESSAGE = (
    "Attempted to generate <b>{rarity} {display_name}</b> for @{username}, but something broke.\n\n"
    "Awarded <b>{spin_amount} spins</b> as compensation."
)

BURN_RESULT_MESSAGE = (
    "@{username} burned <b>{rarity} {display_name}</b> and received <b>{spin_amount} spins!</b>"
)

MINESWEEPER_VICTORY_PENDING_MESSAGE = (
    "@{username} won a <b>{rarity} {display_name}</b> in Minesweeper!\n\nGenerating card..."
)

MINESWEEPER_VICTORY_RESULT_MESSAGE = (
    "@{username} won a <b>{rarity} {display_name}</b> in Minesweeper!\n\n"
    "<b>[{card_id}] {modifier} {base_name}</b>\n"
    "Rarity: <b>{rarity}</b>\n"
    "Set: <b>{set_name}</b>"
)

MINESWEEPER_VICTORY_FAILURE_MESSAGE = (
    "@{username} won a {rarity} {display_name} in Minesweeper!\n\n" "Card generation failed."
)

MINESWEEPER_LOSS_MESSAGE = "@{username} lost 💥 <b>{card_title}</b> 💥 in Minesweeper!"

MINESWEEPER_BET_MESSAGE = "@{username} bet <b>{card_title}</b> in Minesweeper!"

RTB_RESULT_MESSAGE = "@{username} {action} <b>{amount} spins ({multiplier}x)</b> in Ride the Bus!"

ACHIEVEMENT_NOTIFICATION_MESSAGE = (
    "@{username} received <b>{achievement_name}</b> achievement:\n\n<i>{achievement_desc}</i>"
)

LOCK_USAGE_MESSAGE = (
    "Usage: /lock <card_id>.\n\n"
    "Lock or unlock a card you own.\n\n"
    "Claim points cost varies by rarity:\n"
    f"{LOCK_COST_SUMMARY}"
)

REFRESH_USAGE_MESSAGE = (
    "Usage: /refresh <card_id>.\n\n"
    "Re-generate the image for a card you own.\n\n"
    "Each refresh instantly creates two new options so you can pick your favorite.\n\n"
    "Claim points cost varies by rarity:\n"
    f"{REFRESH_COST_SUMMARY}"
)
REFRESH_DM_RESTRICTED_MESSAGE = "Refreshing cards is only available in the group chat."
REFRESH_INVALID_ID_MESSAGE = "Invalid card ID. Please provide a numeric card ID."
REFRESH_CARD_NOT_FOUND_MESSAGE = "Card not found. Check the ID and try again."
REFRESH_NOT_YOURS_MESSAGE = "You can only refresh cards you currently own."
REFRESH_CHAT_MISMATCH_MESSAGE = "This card doesn't belong to this chat."
REFRESH_INSUFFICIENT_BALANCE_MESSAGE = (
    "You need at least {cost} claim points to refresh this card. Your balance: {balance} points."
)
REFRESH_CONFIRM_MESSAGE = (
    "<b>{card_title}</b>\n\n"
    "Generate two new image options for this card?\n\n"
    "This will cost <b>{cost} claim points</b> for a single refresh.\n\n"
    "Your current balance: <b>{balance} points</b>"
)
REFRESH_CANCELLED_MESSAGE = "<b>{card_title}</b>\n\nRefresh cancelled."
REFRESH_ALREADY_RUNNING_MESSAGE = "You already have a refresh in progress."
REFRESH_PROCESSING_MESSAGE = "<b>{card_title}</b>\n\n<i>Generating new image options...</i>"
REFRESH_OPTIONS_READY_MESSAGE = (
    "<b>{card_title}</b>\n\n"
    "Select an image to keep for this card.\n\n"
    "Remaining balance: <b>{remaining_balance} points</b>."
)
REFRESH_FAILURE_MESSAGE = (
    "<b>{card_title}</b>\n\n"
    "Refresh failed. Image generation is unavailable right now. Your claim points were refunded."
)
REFRESH_SUCCESS_MESSAGE = (
    "<b>{card_title}</b>\n\n"
    "Saved Option {selection}!\n\n"
    "Remaining balance: <b>{remaining_balance} points</b>."
)
REFRESH_ABORTED_MESSAGE = (
    "<b>{card_title}</b>\n\n"
    "Refresh cancelled. Original image kept and claim points remain spent."
)
