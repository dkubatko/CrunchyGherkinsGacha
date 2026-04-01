import json
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

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
BASE_IMAGE_PATH = config["BASE_IMAGE_PATH"]
CARD_TEMPLATES_PATH = config["CARD_TEMPLATES_PATH"]
SLOT_CARD_WIN_CHANCE = config["SLOT_CARD_WIN_CHANCE"]
SLOT_ASPECT_WIN_CHANCE = config.get("SLOT_ASPECT_WIN_CHANCE", 0.04)
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

# Daily bonus / megaspin constants (from config.json)
DAILY_BONUS_RESET_HOUR_PDT = config.get("DAILY_BONUS_RESET_HOUR_PDT", 6)
DAILY_BONUS_PROGRESSION = config.get("DAILY_BONUS_PROGRESSION", [10, 15, 20, 25, 30, 35, 40])
SPINS_FOR_MEGASPIN = config.get("SPINS_FOR_MEGASPIN", 100)

# Environment-sourced settings
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://localhost:5432/gacha")
CURRENT_SEASON = int(os.getenv("CURRENT_SEASON", "0"))

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

# ---------------------------------------------------------------------------
# Prompt template loading — prompts live in bot/prompts/*.md
# ---------------------------------------------------------------------------
_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")


@lru_cache(maxsize=None)
def _load_prompt(filename: str) -> str:
    """Load a prompt template from bot/prompts/."""
    with open(os.path.join(_PROMPTS_DIR, filename), encoding="utf-8") as f:
        return f.read().strip()


UNIQUE_ASPECT_ADDENDUM = _load_prompt("unique_aspect.md")
SLOT_MACHINE_INSTRUCTION = _load_prompt("slot_icon.md")
SET_SLOT_ICON_PROMPT = _load_prompt("set_slot_icon.md")
ASPECT_GENERATION_PROMPT = _load_prompt("aspect_sphere.md")
BASE_CARD_GENERATION_PROMPT = _load_prompt("base_card.md")
EQUIP_GENERATION_PROMPT = _load_prompt("equip_card.md")
REFRESH_EQUIPPED_PROMPT = _load_prompt("refresh_card.md")

ASPECT_SET_CONTEXT = (
    "\n- This aspect belongs to the themed set {set_details}."
    " Interpret the aspect name within that thematic context."
)

REACTION_IN_PROGRESS = "🤔"

COLLECTION_CAPTION = (
    "<b>{lock_icon}🃏 [{card_id}] {card_title}</b>\n"
    "Rarity: <b>{rarity}</b>\n\n"
    "<i>Showing {current_index}/{total_cards} owned by @{username}</i>"
)

CARD_CAPTION_BASE = "<b>🃏 [{card_id}] {card_title}</b>\nRarity: <b>{rarity}</b>"
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

# Aspect roll caption templates
ASPECT_CAPTION_BASE = (
    "<b>🔮 [{aspect_id}] {aspect_name}</b>\nRarity: <b>{rarity}</b>\nSet: <b>{set_name}</b>"
)
ASPECT_STATUS_UNCLAIMED = "\n\n<i>Unclaimed</i>"
ASPECT_STATUS_CLAIMED = "\n\n<i>Claimed by @{username}</i>"
ASPECT_STATUS_LOCKED = "\n\n<i>Locked from re-rolling</i>"
ASPECT_STATUS_REROLLING = "\n\n<b>Rerolling...</b>"
ASPECT_STATUS_REROLLED = (
    "\n\n<i>Rerolled from <b>{original_rarity}</b> to <b>{downgraded_rarity}</b></i>"
)
ASPECT_STATUS_ATTEMPTED = "\n<i>Attempted by: {users}</i>"
ASPECT_STATUS_PRE_CLAIM_MESSAGES = [
    "Shaping the sphere...",
    "Swirling the essence...",
    "Infusing the theme...",
    "Polishing the glass...",
    "Sealing the magic...",
    "Channeling the vibes...",
    "Consulting the stars...",
    "Condensing the aura...",
    "Spinning the globe...",
    "Tinting the crystal...",
    "Taunting the players...",
    "Getting unstuck...",
    "Messing around...",
    "Almost ready...",
    "Just a moment...",
]
PRE_CLAIM_ROTATION_INTERVAL = config.get(
    "PRE_CLAIM_ROTATION_INTERVAL", 1.5
)  # Seconds between message rotations

# Claim unlock delay configuration (random delay in seconds)
CLAIM_UNLOCK_DELAY_LOW = config.get("CLAIM_UNLOCK_DELAY_LOW", 3)  # Minimum delay in seconds
CLAIM_UNLOCK_DELAY_HIGH = config.get("CLAIM_UNLOCK_DELAY_HIGH", 6)  # Maximum delay in seconds

# Roll type weights (base_card vs aspect)
ROLL_TYPE_WEIGHTS = config.get("ROLL_TYPE_WEIGHTS", {"base_card": 10, "aspect": 90})

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


def get_recycle_cost(rarity_name: str) -> int:
    """Return how many items must be burned to recycle up to the next rarity.

    The requirement is determined by the ``recycle_cost`` of the target
    (upgrade) rarity in ``config.json``.
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
    "Usage: /recycle [aspects|cards] [rarity]\n\n"
    "Aspects: 3C→1R, 3R→1E, 4E→1L\n"
    "Cards: 3C→1R, 3R→1E, 4E→1L"
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
    "Burn <b>🃏 [{card_id}] {rarity} {card_title}</b> for <b>{spin_reward} spins</b>?"
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

# ---------------------------------------------------------------------------
# Aspect Burn / Lock / Recycle constants
# ---------------------------------------------------------------------------

ASPECT_BURN_USAGE_MESSAGE = (
    "Usage: /burn <aspect_id>. Burns an aspect you own in this chat for spins."
)
ASPECT_BURN_DM_RESTRICTED_MESSAGE = "Burning aspects is only available in the group chat."
ASPECT_BURN_INVALID_ID_MESSAGE = "Invalid aspect ID. Please provide a numeric aspect ID."
ASPECT_BURN_NOT_FOUND_MESSAGE = "Aspect not found. Check the ID and try again."
ASPECT_BURN_NOT_YOURS_MESSAGE = "You can only burn aspects you currently own."
ASPECT_BURN_CHAT_MISMATCH_MESSAGE = "This aspect doesn't belong to this chat."
ASPECT_BURN_LOCKED_MESSAGE = "This aspect is locked. Unlock it first before burning."
ASPECT_BURN_EQUIPPED_MESSAGE = "This aspect is equipped on a card. Unequip it first before burning."
ASPECT_BURN_CONFIRM_MESSAGE = "Burn <b>🔮 {aspect_title}</b> for <b>{spin_reward} spins</b>?"
ASPECT_BURN_CANCELLED_MESSAGE = "Burn cancelled."
ASPECT_BURN_ALREADY_RUNNING_MESSAGE = "You already have a burn in progress."
ASPECT_BURN_PROCESSING_MESSAGE = "Burning aspect..."
ASPECT_BURN_FAILURE_MESSAGE = "Burn failed. Please try again later."
ASPECT_BURN_SUCCESS_MESSAGE = (
    "Burn complete! Awarded <b>{spin_reward} spins</b>.\n"
    "New spin balance: <b>{new_spin_total}</b>."
)

LOCK_COMBINED_USAGE_MESSAGE = (
    "Usage:\n"
    "  /lock <aspect_id> — Lock/unlock an aspect\n"
    "  /lock card <card_id> — Lock/unlock a card\n\n"
    "Claim points cost varies by rarity:\n"
    f"{LOCK_COST_SUMMARY}"
)
ASPECT_LOCK_USAGE_MESSAGE = LOCK_COMBINED_USAGE_MESSAGE
ASPECT_LOCK_NOT_FOUND_MESSAGE = "Aspect not found. Check the ID and try again."
ASPECT_LOCK_NOT_YOURS_MESSAGE = "You can only lock aspects you currently own."

CARD_LOCK_NOT_FOUND_MESSAGE = "Card not found. Check the ID and try again."
CARD_LOCK_NOT_YOURS_MESSAGE = "You can only lock cards you currently own."
CARD_LOCK_CHAT_MISMATCH_MESSAGE = "This card doesn't belong to this chat."

ASPECT_RECYCLE_USAGE_MESSAGE = (
    "Usage: /recycle [aspects|cards] [rarity]\n\n"
    "Aspects: 3C\u21921R, 3R\u21921E, 4E\u21921L\n"
    "Cards: 3C\u21921R, 3R\u21921E, 4E\u21921L"
)
ASPECT_RECYCLE_DM_RESTRICTED_MESSAGE = "Recycling aspects is only available in the group chat."
ASPECT_RECYCLE_SELECT_RARITY_MESSAGE = "Select <b>aspect rarity</b> to recycle"
ASPECT_RECYCLE_CONFIRM_MESSAGE = "Burn {burn_count} unlocked <b>{rarity}</b> aspects to generate 1 <b>{upgraded_rarity}</b> aspect?"
ASPECT_RECYCLE_INSUFFICIENT_MESSAGE = (
    "You need at least {required} unlocked {rarity} aspects in this chat to recycle."
)
ASPECT_RECYCLE_ALREADY_RUNNING_MESSAGE = "You already have a recycle in progress."
ASPECT_RECYCLE_NOT_YOURS_MESSAGE = "This recycle prompt isn't for you!"
ASPECT_RECYCLE_UNKNOWN_RARITY_MESSAGE = (
    "Unknown rarity. Please choose one of common, rare, or epic."
)
ASPECT_RECYCLE_FAILURE_NOT_ENOUGH = "Recycle failed: not enough unlocked aspects remaining."
ASPECT_RECYCLE_FAILURE_IMAGE = (
    "Recycle failed: image generation is unavailable right now. Your aspects were not burned."
)
ASPECT_RECYCLE_FAILURE_UNEXPECTED = (
    "An unexpected error occurred while recycling aspects. Try again later."
)

CREATE_USAGE_MESSAGE = "Usage: /create &lt;AspectName&gt;\n[optional description]\n\nCreates a <b>Unique</b> aspect by burning {cost} unlocked Legendary aspects.\n\nYou can add a description (up to 300 characters) on a new line to guide the art."
CREATE_DM_RESTRICTED_MESSAGE = "Creating unique aspects is only available in the group chat."
CREATE_CONFIRM_MESSAGE = "Burn {cost} unlocked <b>Legendary</b> aspects to create <b>Unique</b> aspect <b>🔮 {aspect_name}</b>?"
CREATE_DUPLICATE_UNIQUE_NAME_MESSAGE = (
    "The name '<b>{aspect_name}</b>' has already been used for another Unique aspect in this chat. "
    "Please choose a different name."
)
CREATE_INSUFFICIENT_ASPECTS_MESSAGE = "You need at least {required} unlocked, unequipped Legendary aspects in this chat to create a Unique aspect."
CREATE_ALREADY_RUNNING_MESSAGE = "You already have a creation in progress."
CREATE_NOT_YOURS_MESSAGE = "This creation prompt isn't for you!"
CREATE_FAILURE_IMAGE = (
    "Creation failed: image generation is unavailable right now. Your aspects were not burned."
)
CREATE_FAILURE_UNEXPECTED = (
    "An unexpected error occurred while creating the aspect. Try again later."
)
CREATE_SUCCESS_MESSAGE = "Successfully created <b>Unique</b> aspect <b>🔮 {aspect_name}</b>!"
CREATE_CANCELLED_MESSAGE = "Creation cancelled."
CREATE_PROCESSING_MESSAGE = "Creating <b>Unique</b> aspect..."

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

# Aspect trade messages
ASPECT_TRADE_REQUEST_MESSAGE = (
    "Aspect trade requested:\n\n"
    "@{user1_username}'s\n<b>{aspect1_title}</b>\n\n"
    "🔄\n\n"
    "@{user2_username}'s\n<b>{aspect2_title}</b>"
)

ASPECT_TRADE_COMPLETE_MESSAGE = (
    "Aspect trade completed:\n\n"
    "@{user1_username}'s\n<b>{aspect1_title}</b>\n\n"
    "🤝\n\n"
    "@{user2_username}'s\n<b>{aspect2_title}</b>"
)

ASPECT_TRADE_REJECTED_MESSAGE = (
    "Aspect trade rejected:\n\n"
    "@{user1_username}'s\n<b>{aspect1_title}</b>\n\n"
    "🚫\n\n"
    "@{user2_username}'s\n<b>{aspect2_title}</b>"
)

ASPECT_TRADE_CANCELLED_MESSAGE = (
    "Aspect trade cancelled:\n\n"
    "@{user1_username}'s\n<b>{aspect1_title}</b>\n\n"
    "❌\n\n"
    "@{user2_username}'s\n<b>{aspect2_title}</b>"
)

# Slots aspect victory messages
SLOTS_ASPECT_VICTORY_PENDING_MESSAGE = (
    "@{username} won a <b>{rarity} {set_name}</b> aspect in slots!\n\nGenerating aspect..."
)

SLOTS_ASPECT_VICTORY_RESULT_MESSAGE = (
    "@{username} won a <b>{rarity} {set_name}</b> aspect in slots!\n\n"
    "<b>🔮 [{aspect_id}] {aspect_name}</b>\n"
    "Rarity: <b>{rarity}</b>\n"
    "Set: <b>{set_name}</b>"
)

SLOTS_ASPECT_VICTORY_FAILURE_MESSAGE = (
    "@{username} won a {rarity} aspect in slots!\n\nAspect generation failed."
)

SLOTS_VICTORY_PENDING_MESSAGE = (
    "@{username} won a <b>{rarity} {display_name}</b> in slots!\n\nGenerating card..."
)

SLOTS_VICTORY_RESULT_MESSAGE = (
    "@{username} won a <b>{rarity} {display_name}</b> in slots!\n\n"
    "<b>🃏 [{card_id}] {base_name}</b>\n"
    "Rarity: <b>{rarity}</b>"
)

SLOTS_VICTORY_FAILURE_MESSAGE = (
    "@{username} won a {rarity} {display_name} in slots!\n\nCard generation failed."
)

MEGASPIN_VICTORY_PENDING_MESSAGE = "@{username} used a <b>megaspin</b> and won a <b>{rarity} {display_name}</b>!\n\nGenerating card..."

MEGASPIN_VICTORY_RESULT_MESSAGE = (
    "@{username} used a <b>megaspin</b> and won a <b>{rarity} {display_name}</b>!\n\n"
    "<b>🃏 [{card_id}] {base_name}</b>\n"
    "Rarity: <b>{rarity}</b>"
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
    "<b>🃏 [{card_id}] {base_name}</b>\n"
    "Rarity: <b>{rarity}</b>"
)

MINESWEEPER_VICTORY_FAILURE_MESSAGE = (
    "@{username} won a {rarity} {display_name} in Minesweeper!\n\n" "Card generation failed."
)

MINESWEEPER_LOSS_MESSAGE = "@{username} lost <b>{card_title}</b> in Minesweeper!"

MINESWEEPER_BET_MESSAGE = "@{username} bet <b>{card_title}</b> in Minesweeper!"

RTB_RESULT_MESSAGE = "@{username} {action} <b>{amount} spins ({multiplier}x)</b> in Ride the Bus!"

ACHIEVEMENT_NOTIFICATION_MESSAGE = (
    "@{username} received <b>{achievement_name}</b> achievement:\n\n<i>{achievement_desc}</i>"
)

LOCK_USAGE_MESSAGE = LOCK_COMBINED_USAGE_MESSAGE

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

# ---------------------------------------------------------------------------
# Equip constants
# ---------------------------------------------------------------------------

EQUIP_USAGE_MESSAGE = (
    "Usage: /equip &lt;aspect_id&gt; &lt;card_id&gt; [name]\n\n"
    "Equip an aspect onto a card to transform it.\n\n"
    "• <b>aspect_id</b> — the ID of the aspect to equip\n"
    "• <b>card_id</b> — the ID of the card to equip it on\n"
    "• <b>name</b> (optional) — custom name prefix for the card (defaults to aspect name)\n\n"
    "Aspect rarity must be ≤ card rarity (Unique aspects can go on any card).\n"
    "Maximum 5 aspects per card."
)
EQUIP_DM_RESTRICTED_MESSAGE = "Equipping aspects is only available in the group chat."
EQUIP_INVALID_IDS_MESSAGE = "Invalid IDs. Both aspect ID and card ID must be numbers."
EQUIP_ASPECT_NOT_FOUND_MESSAGE = "Aspect not found. Check the ID and try again."
EQUIP_CARD_NOT_FOUND_MESSAGE = "Card not found. Check the ID and try again."
EQUIP_NOT_YOUR_ASPECT_MESSAGE = "You can only equip aspects you currently own."
EQUIP_NOT_YOUR_CARD_MESSAGE = "You can only equip aspects onto cards you currently own."
EQUIP_CHAT_MISMATCH_MESSAGE = "Both the aspect and card must belong to this chat."
EQUIP_CARD_LOCKED_MESSAGE = "Cannot equip onto a locked card. Unlock it first."
EQUIP_ASPECT_LOCKED_MESSAGE = "Cannot equip a locked aspect. Unlock it first."
EQUIP_ASPECT_EQUIPPED_MESSAGE = "This aspect is already equipped on a card."
EQUIP_CAPACITY_MESSAGE = "This card already has 5 aspects equipped (maximum)."
EQUIP_RARITY_MISMATCH_MESSAGE = (
    "Rarity mismatch: a <b>{aspect_rarity}</b> aspect cannot be equipped "
    "on a <b>{card_rarity}</b> card. Aspect rarity must be equal to or lower than card rarity."
)
EQUIP_NAME_TOO_LONG_MESSAGE = "Name prefix is too long. Please keep it under 30 characters."
EQUIP_NAME_INVALID_CHARS_MESSAGE = "Name prefix contains invalid characters. Avoid HTML/markdown special characters (<, >, &, *, _, `)."
EQUIP_CONFIRM_MESSAGE = (
    "Equip <b>🔮 {aspect_title}</b> "
    "onto <b>🃏 {card_title}</b>?\n\n"
    "Card will be renamed to: <b>{new_title}</b>\n"
    "{equipped_aspects}"
)
EQUIP_CANCELLED_MESSAGE = "Equip cancelled."
EQUIP_ALREADY_RUNNING_MESSAGE = "You already have an equip in progress."
EQUIP_NOT_YOURS_MESSAGE = "This equip prompt isn't for you!"
EQUIP_CRAFTING_MESSAGE = (
    "<b>Crafting...</b>\n\n"
    "Equipping <b>🔮 {aspect_title}</b> onto <b>🃏 {card_title}</b>...\n\n"
    "<i>Generating new card art — this may take a moment.</i>"
)
EQUIP_DB_FAILURE_MESSAGE = (
    "Equip failed. The aspect or card may no longer meet the requirements. "
    "Please check and try again."
)
EQUIP_SUCCESS_MESSAGE = (
    "<b>Equip complete!</b>\n\n"
    "<b>🃏 [{card_id}] {new_title}</b>\n"
    "Rarity: <b>{rarity}</b>\n"
    "{equipped_aspects}"
)
EQUIP_IMAGE_FAILURE_MESSAGE = (
    "Aspect equipped successfully, but image generation failed.\n\n"
    "<b>🃏 [{card_id}] {new_title}</b>\n"
    "Rarity: <b>{rarity}</b>\n"
    "{equipped_aspects}\n\n"
    "<i>Use /refresh to regenerate the card art.</i>"
)
