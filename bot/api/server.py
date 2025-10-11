import asyncio
import base64
import os
import sys
import logging
import hmac
import hashlib
import uvicorn
import urllib.parse
from io import BytesIO
from typing import List, Optional, Dict, Any, Tuple, Set
from telegram.constants import ParseMode
from fastapi import FastAPI, HTTPException, Header, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Add project root to sys.path to allow importing from bot
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils import database, gemini, rolling
from utils.database import Card as APICard
from settings.constants import (
    TRADE_REQUEST_MESSAGE,
    RARITIES,
    SLOTS_VICTORY_PENDING_MESSAGE,
    SLOTS_VICTORY_RESULT_MESSAGE,
    SLOTS_VICTORY_FAILURE_MESSAGE,
    SLOTS_VICTORY_REFUND_MESSAGE,
    SLOTS_VIEW_IN_APP_LABEL,
    SLOT_WIN_CHANCE,
    SLOT_CLAIM_CHANCE,
    BURN_RESULT_MESSAGE,
)
from utils.miniapp import encode_single_card_token

# Initialize logger
logger = logging.getLogger(__name__)

# Global bot token and debug mode - will be set by the main bot
bot_token = None
debug_mode = False


def set_bot_token(token, is_debug=False):
    """Set the bot token for creating bot instances."""
    global bot_token, debug_mode
    bot_token = token
    debug_mode = is_debug


app = FastAPI()

DEBUG_MODE = "--debug" in sys.argv or os.getenv("DEBUG", "").lower() in ("true", "1", "yes")

MINIAPP_URL = os.getenv("DEBUG_MINIAPP_URL" if DEBUG_MODE else "MINIAPP_URL")

gemini_util = gemini.GeminiUtil()


MAX_SLOT_VICTORY_IMAGE_RETRIES = 2


class UserSummary(BaseModel):
    user_id: int
    username: Optional[str] = None
    display_name: Optional[str] = None


class UserCollectionResponse(BaseModel):
    user: UserSummary
    cards: List[APICard]


class CardImagesRequest(BaseModel):
    card_ids: List[int]


class CardImageResponse(BaseModel):
    card_id: int
    image_b64: str


class ShareCardRequest(BaseModel):
    card_id: int
    user_id: int


class LockCardRequest(BaseModel):
    card_id: int
    user_id: int
    chat_id: str
    lock: bool  # True to lock, False to unlock


class BurnCardRequest(BaseModel):
    card_id: int
    user_id: int
    chat_id: str


class BurnCardResponse(BaseModel):
    success: bool
    message: str
    spins_awarded: int
    new_spin_total: int


class SlotSymbolSummary(BaseModel):
    id: int
    display_name: Optional[str] = None
    slot_iconb64: Optional[str] = None
    type: str  # "user", "character", or "claim"


class SlotsVictorySource(BaseModel):
    id: int
    type: str


class SlotsVictoryRequest(BaseModel):
    user_id: int
    chat_id: str
    rarity: str
    source: SlotsVictorySource


class SlotsClaimWinRequest(BaseModel):
    user_id: int
    chat_id: str
    amount: int


class SlotsClaimWinResponse(BaseModel):
    success: bool
    balance: int


class SpinsRequest(BaseModel):
    user_id: int
    chat_id: str


class SpinsResponse(BaseModel):
    spins: int
    success: bool = True
    next_refresh_time: Optional[str] = None


class ClaimBalanceResponse(BaseModel):
    balance: int
    user_id: int
    chat_id: str


class BurnRewardsResponse(BaseModel):
    rewards: Dict[str, int]


class ConsumeSpinResponse(BaseModel):
    success: bool
    spins_remaining: Optional[int] = None
    message: Optional[str] = None


class SlotSymbolInfo(BaseModel):
    id: int
    type: str  # "user", "character", or "claim"


class SlotVerifyRequest(BaseModel):
    user_id: int
    chat_id: str
    random_number: int
    symbols: List[SlotSymbolInfo]


class SlotVerifyResponse(BaseModel):
    is_win: bool
    slot_results: List[SlotSymbolInfo]
    rarity: Optional[str] = None


_RARITY_WEIGHT_PAIRS: List[Tuple[str, int]] = [
    (name, int(details.get("weight", 0)))
    for name, details in RARITIES.items()
    if isinstance(details, dict) and int(details.get("weight", 0)) > 0
]
_RARITY_TOTAL_WEIGHT = sum(weight for _, weight in _RARITY_WEIGHT_PAIRS)


def _pick_slot_rarity(random_module) -> str:
    """Select a rarity based on configured weights."""
    if not _RARITY_WEIGHT_PAIRS or _RARITY_TOTAL_WEIGHT <= 0:
        # Fall back to the first configured rarity or Common
        return next(iter(RARITIES.keys()), "Common")

    threshold = random_module.uniform(0, _RARITY_TOTAL_WEIGHT)
    cumulative = 0.0
    for name, weight in _RARITY_WEIGHT_PAIRS:
        cumulative += weight
        if threshold <= cumulative:
            return name

    # Numeric instability fallback
    return _RARITY_WEIGHT_PAIRS[-1][0]


def validate_telegram_init_data(init_data: str) -> Optional[Dict[str, Any]]:
    """
    Validate Telegram WebApp init data according to:
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

    Args:
        init_data: URL-encoded init data from Telegram WebApp

    Returns:
        Dictionary with parsed and validated data, or None if validation fails
    """
    global bot_token

    if not bot_token:
        logger.error("Bot token not available for init data validation")
        return None

    try:
        # Parse URL-encoded data
        parsed_data = urllib.parse.parse_qs(init_data)

        # Extract hash and other data
        received_hash = parsed_data.get("hash", [None])[0]
        if not received_hash:
            logger.warning("No hash found in init data")
            return None

        # Remove hash from data for validation
        data_check_string_parts = []
        for key in sorted(parsed_data.keys()):
            if key != "hash":
                values = parsed_data[key]
                for value in values:
                    data_check_string_parts.append(f"{key}={value}")

        data_check_string = "\n".join(data_check_string_parts)

        # Create secret key from bot token
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()

        # Calculate expected hash
        expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        # Verify hash
        if not hmac.compare_digest(received_hash, expected_hash):
            logger.warning("Init data hash validation failed")
            return None

        # Parse user data if present
        user_data = None
        if "user" in parsed_data:
            import json

            try:
                user_data = json.loads(parsed_data["user"][0])
            except (json.JSONDecodeError, IndexError):
                logger.warning("Failed to parse user data from init data")
                return None

        # Parse auth_date and check if not too old (optional, but recommended)
        auth_date = parsed_data.get("auth_date", [None])[0]
        if auth_date:
            try:
                import time

                auth_timestamp = int(auth_date)
                current_timestamp = int(time.time())
                # Check if auth_date is not older than 24 hours
                if current_timestamp - auth_timestamp > 24 * 60 * 60:
                    logger.warning("Init data is too old (older than 24 hours)")
                    return None
            except (ValueError, TypeError):
                logger.warning("Invalid auth_date in init data")
                return None

        return {
            "user": user_data,
            "auth_date": auth_date,
            "query_id": parsed_data.get("query_id", [None])[0],
            "chat_instance": parsed_data.get("chat_instance", [None])[0],
            "chat_type": parsed_data.get("chat_type", [None])[0],
            "start_param": parsed_data.get("start_param", [None])[0],
        }

    except Exception as e:
        logger.error(f"Error validating init data: {e}")
        return None


def extract_init_data_from_header(authorization: Optional[str]) -> Optional[str]:
    """Extract init data from Authorization header."""
    if not authorization:
        return None

    # Handle both "Bearer <initdata>" and direct initdata formats
    if authorization.startswith("Bearer "):
        return authorization[7:]
    elif authorization.startswith("tma "):  # Telegram Mini App prefix
        return authorization[4:]
    else:
        return authorization


# FastAPI Dependency Functions for Auth
async def get_validated_user(
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> Dict[str, Any]:
    """
    FastAPI dependency that validates Telegram mini app authorization.
    Returns the validated user data dictionary.
    """
    if not authorization:
        logger.warning("No authorization header provided")
        raise HTTPException(status_code=401, detail="Authorization header required")

    init_data = extract_init_data_from_header(authorization)
    if not init_data:
        logger.warning("No init data found in authorization header")
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    validated_data = validate_telegram_init_data(init_data)
    if not validated_data or not validated_data.get("user"):
        logger.warning("Invalid Telegram init data provided")
        raise HTTPException(status_code=401, detail="Invalid or expired Telegram data")

    return validated_data


async def verify_user_match(request_user_id: int, validated_user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Helper to verify that the authenticated user matches the request user_id.
    Returns the validated user data if match is successful.
    """
    user_data: Dict[str, Any] = validated_user.get("user") or {}
    auth_user_id = user_data.get("id")

    if not isinstance(auth_user_id, int):
        logger.warning("Missing or invalid user_id in init data")
        raise HTTPException(status_code=400, detail="Invalid user data in init data")

    if auth_user_id != request_user_id:
        logger.warning(f"User ID mismatch (auth: {auth_user_id}, request: {request_user_id})")
        raise HTTPException(status_code=403, detail="Unauthorized request")

    return validated_user


def _normalize_rarity(rarity: Optional[str]) -> Optional[str]:
    if not rarity:
        return None

    rarity_normalized = rarity.strip().lower()
    for configured_rarity in RARITIES.keys():
        if configured_rarity.lower() == rarity_normalized:
            return configured_rarity
    return None


def _decode_image(image_b64: Optional[str]) -> bytes:
    if not image_b64:
        raise ValueError("Missing image data")

    try:
        return base64.b64decode(image_b64)
    except Exception as exc:
        raise ValueError("Invalid base64 image data") from exc


def _build_single_card_url(card_id: int) -> str:
    if not MINIAPP_URL:
        logger.error("MINIAPP_URL not configured; cannot build card link")
        raise HTTPException(status_code=500, detail="Mini app URL not configured")

    share_token = encode_single_card_token(card_id)
    separator = "&" if "?" in MINIAPP_URL else "?"
    return f"{MINIAPP_URL}{separator}startapp={urllib.parse.quote(share_token)}"


def _generate_slot_loss_pattern(
    random_module, symbols: List[SlotSymbolInfo]
) -> List[SlotSymbolInfo]:
    """
    Generate a dramatic slot machine loss pattern.

    Valid patterns:
    - [a, b, c] (all different) - no matching symbols
    - [a, a, b] (first two same, third different) - creates tension with near-miss

    Invalid patterns:
    - [a, b, a] - too cruel, looks like a near-miss sandwich pattern
    - [a, b, b] - not allowed, must be first two same

    Args:
        random_module: Random module instance for generating random numbers
        symbols: List of available SlotSymbolInfo objects

    Returns:
        List of 3 SlotSymbolInfo objects representing the slot results
    """
    symbol_count = len(symbols)

    if symbol_count < 2:
        # Edge case: if only one symbol exists, just return three of them
        return [symbols[0], symbols[0], symbols[0]]

    # Choose loss pattern type
    pattern_type = random_module.choice(["all_different", "two_same_start"])

    def _weighted_choice_symbol(
        exclude_indices: Set[int], near_target_indices: List[int]
    ) -> SlotSymbolInfo:
        """Pick a symbol favouring those closer to the would-be winning targets."""
        candidates = [idx for idx in range(symbol_count) if idx not in exclude_indices]
        if not candidates:
            return symbols[near_target_indices[0]]

        weights: List[float] = []
        for candidate in candidates:
            min_distance = min(abs(candidate - target) for target in near_target_indices)
            # Invert distance (with +1 to avoid division by zero) to weight near misses higher
            weights.append(1.0 / (min_distance + 1.0))

        total_weight = sum(weights)
        if total_weight <= 0:
            return symbols[random_module.choice(candidates)]

        threshold = random_module.random() * total_weight
        cumulative = 0.0
        for candidate, weight in zip(candidates, weights):
            cumulative += weight
            if cumulative >= threshold:
                return symbols[candidate]

        return symbols[candidates[-1]]

    if pattern_type == "all_different" and symbol_count >= 3:
        # Generate three different symbols with weighted near-miss preference
        first_idx = random_module.randint(0, symbol_count - 1)
        first = symbols[first_idx]
        second = _weighted_choice_symbol({first_idx}, [first_idx])
        second_idx = next(
            i for i, s in enumerate(symbols) if s.id == second.id and s.type == second.type
        )
        third = _weighted_choice_symbol({first_idx, second_idx}, [first_idx, second_idx])
        return [first, second, third]
    else:
        # Generate pattern [a, a, b] - first two same, third different
        same_idx = random_module.randint(0, symbol_count - 1)
        same_symbol = symbols[same_idx]
        different_symbol = _weighted_choice_symbol({same_idx}, [same_idx])
        return [same_symbol, same_symbol, different_symbol]  # [a, a, b]


# CORS configuration
allowed_origins = [
    "https://app.crunchygherkins.com",
    "http://localhost:5173",  # For local development
]

if DEBUG_MODE:
    allowed_origins.extend(
        [
            "http://192.168.1.200:5173",  # Local IP for mobile testing
            "https://192.168.1.200:5173",  # HTTPS version if needed
        ]
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


# =============================================================================
# CARD ENDPOINTS
# =============================================================================


@app.get("/cards/burn-rewards", response_model=BurnRewardsResponse)
async def get_burn_rewards(
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get the rarity to spin reward mapping for burning cards."""
    rewards = {}
    for rarity_name, rarity_details in RARITIES.items():
        if isinstance(rarity_details, dict) and "spin_reward" in rarity_details:
            rewards[rarity_name] = rarity_details["spin_reward"]

    return BurnRewardsResponse(rewards=rewards)


@app.get("/cards/all", response_model=List[APICard])
async def get_all_cards_endpoint(
    chat_id: Optional[str] = Query(None, alias="chat_id"),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get all cards that have been claimed."""
    cards = await asyncio.to_thread(database.get_all_cards, chat_id)
    return [APICard(**card.__dict__) for card in cards]


@app.get("/cards/{user_id}", response_model=UserCollectionResponse)
async def get_user_collection(
    user_id: int,
    chat_id: Optional[str] = Query(None, alias="chat_id"),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get all cards owned by a user.

    This endpoint requires authentication via Authorization header with Telegram WebApp initData.
    """
    cards = await asyncio.to_thread(database.get_user_collection, user_id, chat_id)
    user_record = await asyncio.to_thread(database.get_user, user_id)
    username = user_record.username if user_record else None
    display_name = user_record.display_name if user_record else None

    if not username:
        username = await asyncio.to_thread(database.get_username_for_user_id, user_id)

    if not cards and username is None:
        logger.warning(f"No user or cards found for user_id: {user_id}")
        raise HTTPException(status_code=404, detail="User not found")

    api_cards = [APICard(**card.model_dump()) for card in cards]

    return UserCollectionResponse(
        user=UserSummary(
            user_id=user_id,
            username=username,
            display_name=display_name,
        ),
        cards=api_cards,
    )


@app.get("/cards/detail/{card_id}", response_model=APICard)
async def get_card_detail(
    card_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Fetch metadata for a single card."""
    card = await asyncio.to_thread(database.get_card, card_id)
    if not card:
        logger.warning("Card detail requested for non-existent card_id: %s", card_id)
        raise HTTPException(status_code=404, detail="Card not found")

    card_payload = card.model_dump(
        include={
            "id",
            "base_name",
            "modifier",
            "rarity",
            "owner",
            "user_id",
            "file_id",
            "chat_id",
            "created_at",
        }
    )

    return APICard(**card_payload)


@app.post("/cards/share")
async def share_card(
    request: ShareCardRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Share a card to its chat via the Telegram bot."""
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(request.user_id, validated_user)

    global bot_token

    # Extract user data from validated data
    user_data: Dict[str, Any] = validated_user["user"] or {}
    auth_user_id = user_data.get("id")

    card = await asyncio.to_thread(database.get_card, request.card_id)
    if not card:
        logger.warning("Share requested for non-existent card_id: %s", request.card_id)
        raise HTTPException(status_code=404, detail="Card not found")

    card_chat_id = card.chat_id
    if not card_chat_id:
        logger.error("Card %s missing chat_id; cannot share", request.card_id)
        raise HTTPException(status_code=500, detail="Card chat not configured")

    username = user_data.get("username")
    if not username:
        username = await asyncio.to_thread(database.get_username_for_user_id, auth_user_id)

    if not username:
        logger.warning("Unable to resolve username for user_id %s during share", auth_user_id)
        raise HTTPException(status_code=400, detail="Username not found for user")

    card_title = card.title(include_id=True, include_rarity=True)
    if not MINIAPP_URL:
        logger.error("MINIAPP_URL not configured; cannot generate share link")
        raise HTTPException(status_code=500, detail="Mini app URL not configured")

    try:
        from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

        share_token = encode_single_card_token(request.card_id)
        share_url = MINIAPP_URL
        if "?" in MINIAPP_URL:
            separator = "&"
        else:
            separator = "?"
        share_url = f"{MINIAPP_URL}{separator}startapp={urllib.parse.quote(share_token)}"

        if not bot_token:
            logger.error("Bot token not available for share request")
            raise HTTPException(status_code=503, detail="Bot service unavailable")

        bot = Bot(token=bot_token)
        if debug_mode:
            bot._base_url = f"https://api.telegram.org/bot{bot_token}/test"
            bot._base_file_url = f"https://api.telegram.org/file/bot{bot_token}/test"

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("View here", url=share_url)]])

        message = f"@{username} shared card:\n\n<b>{card_title}</b>"

        # Add ownership info if the sharer is not the owner
        if card.owner and card.owner != username:
            message += f"\n\n<i>Owned by @{card.owner}</i>"

        # Get thread_id if available
        thread_id = await asyncio.to_thread(database.get_thread_id, card_chat_id)

        send_params = {
            "chat_id": card_chat_id,
            "text": message,
            "reply_markup": keyboard,
            "parse_mode": ParseMode.HTML,
        }
        if thread_id is not None:
            send_params["message_thread_id"] = thread_id

        await bot.send_message(**send_params)

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to share card %s: %s", request.card_id, e)
        raise HTTPException(status_code=500, detail="Failed to share card")


@app.post("/cards/lock")
async def lock_card(
    request: LockCardRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Lock or unlock a card owned by the user.

    Locking a card costs 1 claim point. Unlocking does not refund the point.
    """
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(request.user_id, validated_user)

    # Extract user data from validated data
    user_data: Dict[str, Any] = validated_user["user"] or {}
    auth_user_id = user_data.get("id")

    # Get the card from database
    card = await asyncio.to_thread(database.get_card, request.card_id)
    if not card:
        logger.warning("Lock requested for non-existent card_id: %s", request.card_id)
        raise HTTPException(status_code=404, detail="Card not found")

    # Verify ownership
    username = user_data.get("username")
    if not username:
        username = await asyncio.to_thread(database.get_username_for_user_id, auth_user_id)

    if not username:
        logger.warning("Unable to resolve username for user_id %s during lock", auth_user_id)
        raise HTTPException(status_code=400, detail="Username not found for user")

    if card.owner != username:
        logger.warning(
            "User %s (%s) attempted to lock card %s owned by %s",
            username,
            auth_user_id,
            request.card_id,
            card.owner,
        )
        raise HTTPException(status_code=403, detail="You do not own this card")

    # Verify user is enrolled in the chat
    chat_id = str(request.chat_id)
    is_member = await asyncio.to_thread(database.is_user_in_chat, chat_id, auth_user_id)
    if not is_member:
        logger.warning("User %s not enrolled in chat %s", auth_user_id, chat_id)
        raise HTTPException(status_code=403, detail="User not enrolled in this chat")

    # Check current lock status
    if request.lock:
        # User wants to lock the card
        if card.locked:
            raise HTTPException(status_code=400, detail="Card is already locked")

        # Check if user has enough claim points
        current_balance = await asyncio.to_thread(database.get_claim_balance, auth_user_id, chat_id)

        if current_balance < 1:
            raise HTTPException(
                status_code=400,
                detail=f"Not enough claim points.\n\nBalance: {current_balance}",
            )

        # Consume 1 claim point
        remaining_balance = await asyncio.to_thread(
            database.reduce_claim_points, auth_user_id, chat_id, 1
        )

        if remaining_balance is None:
            # This shouldn't happen since we checked above, but handle it anyway
            current_balance = await asyncio.to_thread(
                database.get_claim_balance, auth_user_id, chat_id
            )
            raise HTTPException(
                status_code=400,
                detail=f"Not enough claim points.\n\nBalance: {current_balance}",
            )

        # Lock the card
        await asyncio.to_thread(database.set_card_locked, request.card_id, True)

        logger.info(
            "User %s locked card %s. Remaining balance: %s",
            username,
            request.card_id,
            remaining_balance,
        )

        return {
            "success": True,
            "locked": True,
            "balance": remaining_balance,
            "message": "Card locked successfully",
        }
    else:
        # User wants to unlock the card
        if not card.locked:
            raise HTTPException(status_code=400, detail="Card is not locked")

        # Unlock the card (no refund)
        await asyncio.to_thread(database.set_card_locked, request.card_id, False)

        # Get current balance for response
        current_balance = await asyncio.to_thread(database.get_claim_balance, auth_user_id, chat_id)

        logger.info("User %s unlocked card %s", username, request.card_id)

        return {
            "success": True,
            "locked": False,
            "balance": current_balance,
            "message": "Card unlocked successfully",
        }


@app.post("/cards/burn", response_model=BurnCardResponse)
async def burn_card(
    request: BurnCardRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Burn a card owned by the user, removing ownership and awarding spins based on rarity."""
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(request.user_id, validated_user)

    # Extract user data from validated data
    user_data: Dict[str, Any] = validated_user.get("user") or {}
    auth_user_id = user_data.get("id")

    # Get the card from database
    card = await asyncio.to_thread(database.get_card, request.card_id)
    if not card:
        logger.warning("Burn requested for non-existent card_id: %s", request.card_id)
        raise HTTPException(status_code=404, detail="Card not found")

    # Verify ownership
    username = user_data.get("username")
    if not username:
        username = await asyncio.to_thread(database.get_username_for_user_id, auth_user_id)

    if not username:
        logger.warning("Unable to resolve username for user_id %s during burn", auth_user_id)
        raise HTTPException(status_code=400, detail="Username not found for user")

    if card.owner != username:
        logger.warning(
            "User %s (%s) attempted to burn card %s owned by %s",
            username,
            auth_user_id,
            request.card_id,
            card.owner,
        )
        raise HTTPException(status_code=403, detail="You do not own this card")

    # Verify card is associated with the specified chat
    if card.chat_id != str(request.chat_id):
        logger.warning(
            "Card %s chat_id mismatch. Card chat: %s, Request chat: %s",
            request.card_id,
            card.chat_id,
            request.chat_id,
        )
        raise HTTPException(status_code=400, detail="Card is not associated with this chat")

    # Verify user is enrolled in the chat
    chat_id = str(request.chat_id)
    is_member = await asyncio.to_thread(database.is_user_in_chat, chat_id, auth_user_id)
    if not is_member:
        logger.warning("User %s not enrolled in chat %s", auth_user_id, chat_id)
        raise HTTPException(status_code=403, detail="User not enrolled in this chat")

    # Get spin reward for the card's rarity
    rarity_config = RARITIES.get(card.rarity)
    if not rarity_config or not isinstance(rarity_config, dict):
        logger.error("Invalid rarity configuration for card %s: %s", request.card_id, card.rarity)
        raise HTTPException(status_code=500, detail="Invalid card rarity configuration")

    spin_reward = rarity_config.get("spin_reward", 0)
    if spin_reward <= 0:
        logger.error("No spin reward configured for rarity %s", card.rarity)
        raise HTTPException(status_code=500, detail="No spin reward configured for this rarity")

    # Delete the card from the database
    success = await asyncio.to_thread(database.delete_card, request.card_id)

    if not success:
        logger.error("Failed to delete card %s", request.card_id)
        raise HTTPException(status_code=500, detail="Failed to burn card")

    # Award spins to the user
    new_spin_total = await asyncio.to_thread(
        database.increment_user_spins, auth_user_id, chat_id, spin_reward
    )

    if new_spin_total is None:
        logger.error(
            "Failed to award spins to user %s in chat %s after burning card %s",
            auth_user_id,
            chat_id,
            request.card_id,
        )
        # Card is already burned, but spins weren't awarded - this is a critical error
        raise HTTPException(status_code=500, detail="Card burned but failed to award spins")

    logger.info(
        "Card %s (%s %s %s) burned by user %s (%s) in chat %s. Awarded %s spins. New total: %s",
        request.card_id,
        card.rarity,
        card.modifier,
        card.base_name,
        username,
        auth_user_id,
        chat_id,
        spin_reward,
        new_spin_total,
    )

    # Store card details before returning response
    card_display_name = card.title()
    card_rarity = card.rarity

    # Spawn background task to send notification to chat
    asyncio.create_task(
        _process_burn_notification(
            bot_token=bot_token,
            debug_mode=debug_mode,
            username=username,
            card_rarity=card_rarity,
            card_display_name=card_display_name,
            spin_amount=spin_reward,
            chat_id=chat_id,
        )
    )

    return BurnCardResponse(
        success=True,
        message=f"Card burned successfully! Awarded {spin_reward} spins.",
        spins_awarded=spin_reward,
        new_spin_total=new_spin_total,
    )


# =============================================================================
# CARD IMAGE ENDPOINTS
# =============================================================================


@app.get("/cards/image/{card_id}", response_model=str)
async def get_card_image_route(
    card_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get the base64 encoded image for a card."""
    image_b64 = await asyncio.to_thread(database.get_card_image, card_id)
    if not image_b64:
        raise HTTPException(status_code=404, detail="Image not found")
    return image_b64


@app.post("/cards/images", response_model=List[CardImageResponse])
async def get_card_images_route(
    request: CardImagesRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get base64 encoded images for multiple cards in a single batch."""
    card_ids = request.card_ids or []
    unique_card_ids = list(dict.fromkeys(card_ids))

    if not unique_card_ids:
        raise HTTPException(status_code=400, detail="card_ids must contain at least one value")

    if len(unique_card_ids) > 3:
        raise HTTPException(
            status_code=400, detail="A maximum of 3 card IDs can be requested per batch"
        )

    images = await asyncio.to_thread(database.get_card_images_batch, unique_card_ids)

    if not images:
        raise HTTPException(status_code=404, detail="No images found for requested card IDs")

    response_payload = [
        CardImageResponse(card_id=card_id, image_b64=image)
        for card_id, image in images.items()
        if image
    ]

    if not response_payload:
        raise HTTPException(status_code=404, detail="No images found for requested card IDs")

    return response_payload


# =============================================================================
# TRADE ENDPOINTS
# =============================================================================


@app.get("/trade/{card_id}/options", response_model=List[APICard])
async def get_trade_options(
    card_id: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get trade options for a specific card, scoped to the same chat."""
    card = await asyncio.to_thread(database.get_card, card_id)
    if not card:
        logger.warning(f"Requested trade options for non-existent card_id: {card_id}")
        raise HTTPException(status_code=404, detail="Card not found")

    if not card.chat_id:
        logger.warning(f"Card {card_id} has no chat_id; cannot load trade options")
        raise HTTPException(status_code=400, detail="Card is not associated with a chat")

    cards = await asyncio.to_thread(database.get_all_cards, card.chat_id)

    initiating_owner = card.owner
    filtered_cards = [
        card_option
        for card_option in cards
        if card_option.id != card_id
        and card_option.owner is not None
        and card_option.owner != initiating_owner
    ]

    return [APICard(**card_option.__dict__) for card_option in filtered_cards]


@app.post("/trade/{card_id1}/{card_id2}")
async def execute_trade(
    card_id1: int,
    card_id2: int,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Execute a card trade between two cards."""
    global bot_token

    # Get user data from validated init data
    user_data = validated_user["user"]
    user_id = user_data.get("id")

    if not user_id:
        logger.warning(f"Missing user_id in init data for trade {card_id1}/{card_id2}")
        raise HTTPException(status_code=400, detail="Invalid user data in init data")

    # Check if bot token is available
    if not bot_token:
        logger.error("Bot token not available for trade execution")
        raise HTTPException(status_code=503, detail="Bot service unavailable")

    try:
        # Get cards from database
        card1 = await asyncio.to_thread(database.get_card, card_id1)
        card2 = await asyncio.to_thread(database.get_card, card_id2)

        if not card1 or not card2:
            raise HTTPException(status_code=404, detail="One or both card IDs are invalid")

        card1_chat_id = card1.chat_id
        card2_chat_id = card2.chat_id

        if not card1_chat_id or not card2_chat_id:
            logger.error(
                "Missing chat_id on cards %s and %s",
                card_id1,
                card_id2,
            )
            raise HTTPException(status_code=500, detail="Card chat not configured")

        if card1_chat_id != card2_chat_id:
            logger.warning(
                "Trade attempted between cards %s and %s from different chats (%s vs %s)",
                card_id1,
                card_id2,
                card1_chat_id,
                card2_chat_id,
            )
            raise HTTPException(
                status_code=400,
                detail="Both cards must belong to the same chat to trade",
            )
        chat_id = card1_chat_id  # Get current user's username from the validated init data
        current_username = user_data.get("username")
        if not current_username:
            logger.error(f"Username not found in init data for user_id {user_id}")
            raise HTTPException(status_code=400, detail="Username not found in init data")

        # Validate trade
        if card1.owner != current_username:
            raise HTTPException(status_code=403, detail=f"You do not own card {card1.title()}")

        if card2.owner == current_username:
            raise HTTPException(status_code=400, detail=f"You already own card {card2.title()}")

        # Send trade request message with accept/reject buttons
        trade_message = TRADE_REQUEST_MESSAGE.format(
            user1_username=current_username,
            card1_title=card1.title(include_rarity=True),
            user2_username=card2.owner,
            card2_title=card2.title(include_rarity=True),
        )

        # Create inline keyboard with accept/reject buttons, card view links, and cancel button
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [
                InlineKeyboardButton("Accept", callback_data=f"trade_accept_{card_id1}_{card_id2}"),
                InlineKeyboardButton("Reject", callback_data=f"trade_reject_{card_id1}_{card_id2}"),
            ]
        ]

        # Add card view links
        if MINIAPP_URL:
            card1_url = _build_single_card_url(card_id1)
            card2_url = _build_single_card_url(card_id2)
            keyboard.append(
                [
                    InlineKeyboardButton("Card 1", url=card1_url),
                    InlineKeyboardButton("Card 2", url=card2_url),
                ]
            )

        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            # Create a new bot instance to avoid event loop conflicts
            from telegram import Bot

            if debug_mode:
                # Use test environment endpoints when in debug mode
                bot = Bot(token=bot_token)
                # Override the bot's base URLs to use test environment (same as main bot)
                bot._base_url = f"https://api.telegram.org/bot{bot_token}/test"
                bot._base_file_url = f"https://api.telegram.org/file/bot{bot_token}/test"
            else:
                bot = Bot(token=bot_token)

            # Get thread_id for trade notifications, fallback to main if trade not set
            thread_id = await asyncio.to_thread(database.get_thread_id, str(chat_id), "trade")
            if thread_id is None:
                thread_id = await asyncio.to_thread(database.get_thread_id, str(chat_id), "main")

            send_params = {
                "chat_id": chat_id,
                "text": trade_message,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
            }
            if thread_id is not None:
                send_params["message_thread_id"] = thread_id

            # Send message using the new bot instance
            await bot.send_message(**send_params)
        except Exception as e:
            logger.error(f"Failed to send trade request message to chat {chat_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to send trade request")

        return {"success": True, "message": "Trade request sent successfully"}

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Unexpected error in trade endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# USER ENDPOINTS
# =============================================================================


@app.get("/user/{user_id}/claims", response_model=ClaimBalanceResponse)
async def get_user_claim_balance(
    user_id: int,
    chat_id: str = Query(..., description="Chat ID"),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get the current claim balance for a user in a specific chat."""
    try:
        # Verify the authenticated user matches the requested user_id
        await verify_user_match(user_id, validated_user)

        # Get claim balance
        balance = await asyncio.to_thread(database.get_claim_balance, user_id, chat_id)

        return ClaimBalanceResponse(balance=balance, user_id=user_id, chat_id=chat_id)

    except Exception as e:
        logger.error(f"Error getting claim balance for user {user_id} in chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get claim balance")


# =============================================================================
# SLOTS ENDPOINTS
# =============================================================================


@app.get("/slots/spins", response_model=SpinsResponse)
async def get_user_spins(
    user_id: int = Query(..., description="User ID"),
    chat_id: str = Query(..., description="Chat ID"),
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get the current number of spins for a user in a specific chat, with daily refresh logic."""
    try:
        # Verify the authenticated user matches the requested user_id
        await verify_user_match(user_id, validated_user)

        # Get spins with daily refresh logic
        spins_count = await asyncio.to_thread(
            database.get_or_update_user_spins_with_daily_refresh, user_id, chat_id
        )

        # Get next refresh time separately
        next_refresh_time = await asyncio.to_thread(
            database.get_next_spin_refresh, user_id, chat_id
        )

        return SpinsResponse(spins=spins_count, success=True, next_refresh_time=next_refresh_time)

    except Exception as e:
        logger.error(f"Error getting spins for user {user_id} in chat {chat_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get spins")


@app.post("/slots/spins", response_model=ConsumeSpinResponse)
async def consume_user_spin(
    request: SpinsRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Consume one spin for a user in a specific chat."""
    try:
        # Verify the authenticated user matches the requested user_id
        await verify_user_match(request.user_id, validated_user)

        # Attempt to consume a spin
        success = await asyncio.to_thread(
            database.consume_user_spin, request.user_id, request.chat_id
        )

        if success:
            # Get remaining spins after consumption
            remaining_spins = await asyncio.to_thread(
                database.get_or_update_user_spins_with_daily_refresh,
                request.user_id,
                request.chat_id,
            )

            return ConsumeSpinResponse(
                success=True, spins_remaining=remaining_spins, message="Spin consumed successfully"
            )
        else:
            # Get current spins to show in error
            current_spins = await asyncio.to_thread(
                database.get_or_update_user_spins_with_daily_refresh,
                request.user_id,
                request.chat_id,
            )

            return ConsumeSpinResponse(
                success=False, spins_remaining=current_spins, message="No spins available"
            )

    except Exception as e:
        logger.error(
            f"Error consuming spin for user {request.user_id} in chat {request.chat_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to consume spin")


@app.post("/slots/verify", response_model=SlotVerifyResponse)
async def verify_slot_spin(
    request: SlotVerifyRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Verify a slot spin result using server-side randomness and logic."""
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(request.user_id, validated_user)

    # Validate input parameters
    if not request.symbols or len(request.symbols) == 0:
        raise HTTPException(status_code=400, detail="Symbols list cannot be empty")

    symbol_count = len(request.symbols)

    if request.random_number < 0 or request.random_number >= symbol_count:
        raise HTTPException(
            status_code=400,
            detail=f"Random number must be between 0 and {symbol_count - 1}",
        )

    try:
        import random
        import time

        # Use current time and client random number for better entropy
        # Don't set a deterministic seed - let Python use system randomness
        random.seed()  # Reset to system randomness

        # Add some entropy from the request for security
        entropy_source = hash(
            f"{request.user_id}_{request.chat_id}_{request.random_number}_{time.time()}"
        )
        random.seed(entropy_source)

        # Server-side win rate from config (boosted in debug mode)
        win_chance = 0.2 if DEBUG_MODE else SLOT_WIN_CHANCE
        is_card_win = random.random() < win_chance
        rarity: Optional[str] = None
        winning_symbol: Optional[SlotSymbolInfo] = None
        slot_results: List[SlotSymbolInfo] = []
        is_win = False

        if is_card_win:
            # Player wins a card - select a random user or character symbol
            # Filter out claim symbols for card wins
            eligible_symbols = [s for s in request.symbols if s.type != "claim"]

            if not eligible_symbols:
                # Fallback: no eligible symbols, treat as loss
                is_card_win = False
            else:
                # Pick a random eligible symbol
                winning_symbol = random.choice(eligible_symbols)
                rarity = _pick_slot_rarity(random)
                # All three reels show the winning symbol
                slot_results = [winning_symbol, winning_symbol, winning_symbol]
                is_win = True

        if not is_card_win:
            # Check for claim win (only if they didn't win a card)
            claim_chance = 0.5 if DEBUG_MODE else SLOT_CLAIM_CHANCE
            claim_win = random.random() < claim_chance

            if claim_win:
                # Find the claim symbol
                claim_symbols = [s for s in request.symbols if s.type == "claim"]
                if claim_symbols:
                    winning_symbol = claim_symbols[0]  # Should only be one claim symbol
                    # All three reels show the claim symbol
                    slot_results = [winning_symbol, winning_symbol, winning_symbol]
                    is_win = True  # Claim win is still a win!

        # Generate loss pattern if no win
        if not slot_results:
            slot_results = _generate_slot_loss_pattern(random, request.symbols)

        # Build descriptive log message
        if is_card_win and rarity:
            win_type = f"card ({rarity})"
        elif winning_symbol and winning_symbol.type == "claim":
            win_type = "claim point"
        else:
            win_type = "loss"

        logger.info(
            f"Slot verification for user {request.user_id} in chat {request.chat_id}: "
            f"result={win_type}, win_chance={win_chance:.3f}, "
            f"winning_symbol={winning_symbol}, slot_results={[f'{s.type}:{s.id}' for s in slot_results]}"
        )

        return SlotVerifyResponse(is_win=is_win, slot_results=slot_results, rarity=rarity)

    except Exception as e:
        logger.error(
            f"Error verifying slot spin for user {request.user_id} in chat {request.chat_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to verify slot spin")


@app.post("/slots/victory")
async def slots_victory(
    request: SlotsVictoryRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Handle a slot victory by generating a card and sharing it in the chat."""
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(request.user_id, validated_user)

    global bot_token

    # Extract user data from validated data
    user_data: Dict[str, Any] = validated_user["user"] or {}
    auth_user_id = user_data.get("id")

    # Get username
    username = user_data.get("username")
    if not username:
        username = await asyncio.to_thread(database.get_username_for_user_id, auth_user_id)
    if not username:
        logger.warning("Unable to resolve username for user_id %s", auth_user_id)
        raise HTTPException(status_code=400, detail="Username not found for user")

    # Validate request parameters
    normalized_rarity = _normalize_rarity(request.rarity)
    if not normalized_rarity:
        logger.warning("Unsupported rarity '%s' provided", request.rarity)
        raise HTTPException(status_code=400, detail="Unsupported rarity value")

    chat_id = str(request.chat_id).strip()
    if not chat_id:
        logger.warning("Empty chat_id provided for slots victory")
        raise HTTPException(status_code=400, detail="chat_id is required")

    source_type = (request.source.type or "").strip().lower()
    if source_type not in ("user", "character"):
        logger.warning("Unsupported source type '%s'", request.source.type)
        raise HTTPException(status_code=400, detail="Invalid source type")

    if not bot_token:
        logger.error("Bot token not available for slots victory")
        raise HTTPException(status_code=503, detail="Bot service unavailable")

    # Ensure the winner is enrolled in the chat
    is_member = await asyncio.to_thread(database.is_user_in_chat, chat_id, request.user_id)
    if not is_member:
        logger.warning("User %s not enrolled in chat %s", request.user_id, chat_id)
        raise HTTPException(status_code=403, detail="User not enrolled in chat")

    # Get source display name for validation
    if source_type == "user":
        source_user = await asyncio.to_thread(database.get_user, request.source.id)
        if not source_user or not source_user.display_name:
            raise HTTPException(status_code=404, detail="Source user not found or incomplete")
        display_name = source_user.display_name
    else:
        source_character = await asyncio.to_thread(database.get_character_by_id, request.source.id)
        if not source_character or not source_character.name:
            raise HTTPException(status_code=404, detail="Source character not found")
        if str(source_character.chat_id) != chat_id:
            raise HTTPException(status_code=400, detail="Character does not belong to chat")
        display_name = source_character.name

    # All validation passed - respond immediately with success
    response_data = {
        "status": "processing",
        "message": "Slots victory accepted, processing card...",
    }

    # Process card generation in background task (fire-and-forget)
    asyncio.create_task(
        _process_slots_victory_background(
            bot_token=bot_token,
            debug_mode=debug_mode,
            username=username,
            normalized_rarity=normalized_rarity,
            display_name=display_name,
            chat_id=chat_id,
            source_type=source_type,
            source_id=request.source.id,
            user_id=request.user_id,
            gemini_util=gemini_util,
        )
    )

    return response_data


@app.post("/slots/claim-win", response_model=SlotsClaimWinResponse)
async def slots_claim_win(
    request: SlotsClaimWinRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Handle a slot claim win by adding 1 claim point to the user's balance."""
    # Verify the authenticated user matches the requested user_id
    await verify_user_match(request.user_id, validated_user)

    chat_id = str(request.chat_id).strip()
    if not chat_id:
        logger.warning("Empty chat_id provided for slots claim win")
        raise HTTPException(status_code=400, detail="chat_id is required")

    # Ensure the winner is enrolled in the chat
    is_member = await asyncio.to_thread(database.is_user_in_chat, chat_id, request.user_id)
    if not is_member:
        logger.warning("User %s not enrolled in chat %s", request.user_id, chat_id)
        raise HTTPException(status_code=403, detail="User not enrolled in chat")

    try:
        # Add claim points to the user's balance
        amount = max(1, request.amount)  # Ensure at least 1 point is added
        new_balance = await asyncio.to_thread(
            database.increment_claim_balance, request.user_id, chat_id, amount
        )

        logger.info(
            "User %s won %s claim point(s) in chat %s. New balance: %s",
            request.user_id,
            amount,
            chat_id,
            new_balance,
        )

        return SlotsClaimWinResponse(
            success=True,
            balance=new_balance,
        )

    except Exception as exc:
        logger.error(
            "Error adding claim point for user %s in chat %s: %s",
            request.user_id,
            chat_id,
            exc,
        )
        raise HTTPException(status_code=500, detail="Failed to add claim point")


async def _process_slots_victory_background(
    bot_token: str,
    debug_mode: bool,
    username: str,
    normalized_rarity: str,
    display_name: str,
    chat_id: str,
    source_type: str,
    source_id: int,
    user_id: int,
    gemini_util,
):
    """Process slots victory in background after responding to client."""
    rarity_config = RARITIES.get(normalized_rarity, {})
    spin_refund_amount = 0
    if isinstance(rarity_config, dict):
        try:
            spin_refund_amount = int(rarity_config.get("spin_reward", 0) or 0)
        except (TypeError, ValueError):
            spin_refund_amount = 0

    bot = None
    thread_id: Optional[int] = None
    refund_processed = False
    card_generated_and_assigned = False

    try:
        # Initialize bot
        from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

        bot = Bot(token=bot_token)
        if debug_mode:
            bot._base_url = f"https://api.telegram.org/bot{bot_token}/test"
            bot._base_file_url = f"https://api.telegram.org/file/bot{bot_token}/test"

        # Send pending message
        pending_caption = SLOTS_VICTORY_PENDING_MESSAGE.format(
            username=username,
            rarity=normalized_rarity,
            display_name=display_name,
        )

        # Get thread_id if available
        thread_id = await asyncio.to_thread(database.get_thread_id, chat_id)

        send_params = {
            "chat_id": chat_id,
            "text": pending_caption,
            "parse_mode": ParseMode.HTML,
        }
        if thread_id is not None:
            send_params["message_thread_id"] = thread_id

        pending_message = await bot.send_message(**send_params)

        try:
            # Generate card from source with built-in retry support
            generated_card = await asyncio.to_thread(
                rolling.generate_card_from_source,
                source_type,
                source_id,
                gemini_util,
                normalized_rarity,
                max_retries=MAX_SLOT_VICTORY_IMAGE_RETRIES,
            )

            # Add card to database and assign to winner
            card_id = await asyncio.to_thread(
                database.add_card_from_generated,
                generated_card,
                chat_id,
            )

            await asyncio.to_thread(database.set_card_owner, card_id, username, user_id)

            # Mark that card was successfully generated and assigned
            card_generated_and_assigned = True

            # Create final caption and keyboard
            final_caption = SLOTS_VICTORY_RESULT_MESSAGE.format(
                username=username,
                rarity=normalized_rarity,
                display_name=display_name,
                card_id=card_id,
                modifier=generated_card.modifier,
                base_name=generated_card.base_name,
            )

            card_url = _build_single_card_url(card_id)
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton(SLOTS_VIEW_IN_APP_LABEL, url=card_url)]]
            )

            # Send the card image as a new message and delete the pending message
            card_image = base64.b64decode(generated_card.image_b64)

            photo_params = {
                "chat_id": chat_id,
                "photo": card_image,
                "caption": final_caption,
                "reply_markup": keyboard,
                "parse_mode": ParseMode.HTML,
            }
            if thread_id is not None:
                photo_params["message_thread_id"] = thread_id

            card_message = await bot.send_photo(**photo_params)

            # Delete the pending message
            await bot.delete_message(chat_id=chat_id, message_id=pending_message.message_id)

            # Save the file_id from the card message
            if card_message.photo:
                file_id = card_message.photo[-1].file_id
                await asyncio.to_thread(database.update_card_file_id, card_id, file_id)

            logger.info(
                "Successfully processed slots victory for user %s: card %s", username, card_id
            )

        except Exception as exc:
            logger.error("Error processing slots victory for user %s: %s", username, exc)
            # Update pending message with failure
            failure_caption = SLOTS_VICTORY_FAILURE_MESSAGE.format(
                username=username,
                rarity=normalized_rarity,
                display_name=display_name,
            )
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=pending_message.message_id,
                    text=failure_caption,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as edit_exc:
                logger.error("Failed to update failure message: %s", edit_exc)

            # Only refund if card was not generated and assigned
            if spin_refund_amount > 0 and not card_generated_and_assigned:
                refund_processed = await _refund_slots_victory_failure(
                    bot=bot,
                    bot_token=bot_token,
                    debug_mode=debug_mode,
                    username=username,
                    rarity=normalized_rarity,
                    display_name=display_name,
                    chat_id=chat_id,
                    user_id=user_id,
                    spin_amount=spin_refund_amount,
                    thread_id=thread_id,
                )

    except Exception as exc:
        logger.error("Critical error in slots victory background processing: %s", exc)
        # Only refund if card was not generated and assigned
        if spin_refund_amount > 0 and not refund_processed and not card_generated_and_assigned:
            await _refund_slots_victory_failure(
                bot=bot,
                bot_token=bot_token,
                debug_mode=debug_mode,
                username=username,
                rarity=normalized_rarity,
                display_name=display_name,
                chat_id=chat_id,
                user_id=user_id,
                spin_amount=spin_refund_amount,
                thread_id=thread_id,
            )


async def _process_burn_notification(
    bot_token: str,
    debug_mode: bool,
    username: str,
    card_rarity: str,
    card_display_name: str,
    spin_amount: int,
    chat_id: str,
):
    """Send burn notification to chat in background after responding to client."""
    try:
        # Initialize bot
        from telegram import Bot

        bot = Bot(token=bot_token)
        if debug_mode:
            bot._base_url = f"https://api.telegram.org/bot{bot_token}/test"
            bot._base_file_url = f"https://api.telegram.org/file/bot{bot_token}/test"

        # Format the burn result message
        burn_message = BURN_RESULT_MESSAGE.format(
            username=username,
            rarity=card_rarity,
            display_name=card_display_name,
            spin_amount=spin_amount,
        )

        # Get thread_id if available
        thread_id = await asyncio.to_thread(database.get_thread_id, chat_id)

        send_params = {
            "chat_id": chat_id,
            "text": burn_message,
            "parse_mode": ParseMode.HTML,
        }
        if thread_id is not None:
            send_params["message_thread_id"] = thread_id

        await bot.send_message(**send_params)

        logger.info("Sent burn notification for user %s in chat %s", username, chat_id)

    except Exception as exc:
        logger.error(
            "Failed to send burn notification for user %s in chat %s: %s",
            username,
            chat_id,
            exc,
        )


async def _refund_slots_victory_failure(
    bot,
    bot_token: str,
    debug_mode: bool,
    username: str,
    rarity: str,
    display_name: str,
    chat_id: str,
    user_id: int,
    spin_amount: int,
    thread_id: Optional[int] = None,
) -> bool:
    """Refund spins to the user and notify the chat about the failure."""
    if spin_amount <= 0:
        return False

    try:
        new_total = await asyncio.to_thread(
            database.increment_user_spins, user_id, chat_id, spin_amount
        )
    except Exception as exc:
        logger.error(
            "Failed to refund spins after slot victory failure for user %s in chat %s: %s",
            username,
            chat_id,
            exc,
        )
        return False

    if new_total is None:
        logger.error(
            "Spin refund returned None for user %s in chat %s after slot victory failure",
            username,
            chat_id,
        )
        return False

    if bot is None:
        from telegram import Bot

        bot = Bot(token=bot_token)
        if debug_mode:
            bot._base_url = f"https://api.telegram.org/bot{bot_token}/test"
            bot._base_file_url = f"https://api.telegram.org/file/bot{bot_token}/test"

    message = SLOTS_VICTORY_REFUND_MESSAGE.format(
        username=username,
        rarity=rarity,
        display_name=display_name,
        spin_amount=spin_amount,
    )

    try:
        if thread_id is None:
            thread_id = await asyncio.to_thread(database.get_thread_id, chat_id)

        send_params = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": ParseMode.HTML,
        }
        if thread_id is not None:
            send_params["message_thread_id"] = thread_id

        await bot.send_message(**send_params)
    except Exception as exc:
        logger.error(
            "Failed to send slot victory refund notification for user %s in chat %s: %s",
            username,
            chat_id,
            exc,
        )

    return True


# =============================================================================
# CHAT ENDPOINTS
# =============================================================================


@app.get("/chat/{chat_id}/slot-symbols", response_model=List[SlotSymbolSummary])
async def get_slot_symbols_endpoint(
    chat_id: str,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get all slot symbols (users, characters, and claim) for a specific chat with their display names and icons."""
    try:
        # Get users and characters data from database
        data = await asyncio.to_thread(database.get_chat_users_and_characters, chat_id)

        # Load claim icon from file
        claim_icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "slots", "claim_icon.png"
        )

        claim_icon_b64: Optional[str] = None
        try:
            with open(claim_icon_path, "rb") as f:
                claim_icon_bytes = f.read()
                claim_icon_b64 = base64.b64encode(claim_icon_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to load claim icon: {e}")
            # Continue without claim icon rather than failing the whole request

        # Add claim point as a special symbol if icon was loaded successfully
        if claim_icon_b64:
            # Use a special ID that won't conflict with user/character IDs (e.g., -1)
            claim_symbol = {
                "id": -1,
                "display_name": "Claim",
                "slot_iconb64": claim_icon_b64,
                "type": "claim",
            }
            data.append(claim_symbol)

        # Convert to response models and return directly
        return [SlotSymbolSummary(**item) for item in data]

    except Exception as e:
        logger.error(f"Error fetching slot symbols for chat_id {chat_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch slot symbols")


def run_server():
    """Run the FastAPI server."""
    # Disable reload when running in a thread to avoid signal handler issues
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run_server()
