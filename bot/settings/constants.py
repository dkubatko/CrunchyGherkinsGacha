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
SLOT_CLAIM_CHANCE = config["SLOT_CLAIM_CHANCE"]

IMAGE_GENERATOR_INSTRUCTION = """
**Core Requirement: Take the provided 5:7 aspect ratio card template image and completely transform it into a final, detailed collectible trading card.**
Your goal is to use the provided template as a direct base, restyling its elements and filling its content area according to the instructions below.

**--- Guiding Principles ---**
Your main challenge is to find the perfect balance between two critical goals:
1.  **Thematic Transformation:** The card must be a powerful and creative visual representation of its name, "{modification} {name}".
2.  **Character Recognition:** The person depicted on the card must remain clearly and unmistakably recognizable from the input photo.

If these two goals seem to conflict, prioritize making the person recognizable. The final output should feel like a themed portrait of the *specific person*, not a generic character representing the theme.

**1. Art Style & Theme:**
   - **Literal Interpretation:** The visual theme and art style MUST be a direct and literal interpretation of the `{modification}` tag.
   - **AVOID THEME DEFAULTS:** You are strictly forbidden from defaulting to a generic theme (for example **fantasy, magic, arcane, sci-fi, or futuristic**) unless the `{modification}` tag requests that theme explicitly.
   - **Current-Day Grounding:** If `{modification}` is an abstract concept, a personality trait, or a term without an obvious visual theme, your interpretation MUST be grounded in a **contemporary, real-world, and non-speculative context**.
The overall style should be a high-quality, detailed 2D digital illustration.

**2. Card Transformation & Layout:**
   - **Main Artwork:** Completely **replace the large, colored central area** of the template with the character and a richly detailed, themed background. This artwork must extend fully behind the nameplate area.
   - **Restyle Elements:** The template's existing **border and nameplate MUST be restyled** with textures, lighting, and details that match the theme from Section 1. Do not leave them as simple, flat colors.
   - **Layering:** The restyled nameplate must remain an **opaque layer on top** of the main artwork.
   - **Final Frame:** The final image **must retain the exact edge-to-edge dimensions of the provided template**, with no added external padding, margins, or borders.

**3. Character Likeness & Modification:**
   - **Preserve Facial Structure:** To maintain likeness, modifications must apply to the character's **clothing, accessories, hair style, pose, and expression**. The underlying **facial structure, bone shape, and key features (eyes, nose, mouth) MUST be preserved**. Do NOT use the raw, unprocessed photo; render the face in the specified art style while keeping it recognizable.
   - **Direct Modification:** The `{modification}` tag must be interpreted literally. For physical or ethnic attributes, alter the phenotype respectfully while maintaining the core likeness. For identity or cultural attributes, incorporate recognizable symbols or styles into the character's attire, accessories, and the card's background.
   - **Artistic Mandate:** Your creative task is to generate the most powerful and evocative depiction of the theme that is **permissible by content policy.** You must fulfill the prompt's intent by maximizing suggestive and thematic elements (attire, pose, symbolism) without violating policy.

**4. Nameplate & Text Styling:**
   - **Thematic Elements:** The nameplate and text are key thematic elements. Their appearance—including font choice, color, and effects—MUST be styled to match the card's theme (from Section 1).
   - **Complexity Scaling:** The level of ornamentation for both the nameplate and the text is determined by the {creativeness_factor}, as defined in Section 5.
   - **Placement:** The card name "{modification} {name}" MUST be placed horizontally and centered within the restyled nameplate area, as defined by the template.
   - **Exclusivity:** Do NOT include any other text anywhere on the card.

**6. Rarity and Creativeness:**
   - The card's restyled border and accents should be in the {color} gamut, inspired by the template's base color.
   - The "creativeness factor" of {creativeness_factor}/100 dictates the **visual complexity** of the card's design.
     - **Low creativeness (e.g., 10/100):** A simple, clean restyling of the border and minimal background effects.
     - **High creativeness (e.g., 90/100):** A highly ornate, detailed border, dynamic lighting, and complex thematic effects & elements contained within the frame.
   - This factor controls design complexity, **NOT** the art style genre or the degree of deviation from the person's likeness.
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
CARD_STATUS_LOCKED = "\n\n<i>Locked from re-rolling</i>"
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
    "Rarity: <b>{rarity}</b>"
)

SLOTS_VICTORY_FAILURE_MESSAGE = "@{username} won a {rarity} {display_name} in slots!\n\nCard generation failed. Please try again later."

SLOTS_VIEW_IN_APP_LABEL = "View in the app!"

SLOTS_VICTORY_REFUND_MESSAGE = (
    "@{username} attempted to claim a <b>{rarity} {display_name}</b>, but something broke.\n"
    "Awarded <b>{spin_amount} spins</b> as compensation."
)

BURN_RESULT_MESSAGE = (
    "@{username} burned <b>{rarity} {display_name}</b> and received <b>{spin_amount} spins!</b>"
)
