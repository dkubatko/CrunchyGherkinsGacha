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
    SLOTS_VIEW_IN_APP_LABEL,
    SLOT_WIN_CHANCE,
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


class ChatUserCharacterSummary(BaseModel):
    id: int
    display_name: Optional[str] = None
    slot_iconb64: Optional[str] = None
    type: str  # "user" or "character"


class SlotsVictorySource(BaseModel):
    id: int
    type: str


class SlotsVictoryRequest(BaseModel):
    user_id: int
    chat_id: str
    rarity: str
    source: SlotsVictorySource


class SpinsRequest(BaseModel):
    user_id: int
    chat_id: str


class SpinsResponse(BaseModel):
    spins: int
    success: bool = True


class ClaimBalanceResponse(BaseModel):
    balance: int
    user_id: int
    chat_id: str


class ConsumeSpinResponse(BaseModel):
    success: bool
    spins_remaining: Optional[int] = None
    message: Optional[str] = None


class SlotVerifyRequest(BaseModel):
    user_id: int
    chat_id: str
    random_number: int
    symbol_count: int


class SlotVerifyResponse(BaseModel):
    is_win: bool
    results: List[int]  # Array of 3 reel results (indices)
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


def _generate_slot_loss_pattern(random_module, symbol_count: int) -> List[int]:
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
        symbol_count: Total number of available symbols

    Returns:
        List of 3 integers representing the slot results
    """
    if symbol_count < 2:
        # Edge case: if only one symbol exists, just return three of them
        return [0, 0, 0]

    # Choose loss pattern type
    pattern_type = random_module.choice(["all_different", "two_same_start"])

    def _weighted_choice(exclude: Set[int], near_targets: List[int]) -> int:
        """Pick a symbol favouring those closer to the would-be winning targets."""
        candidates = [idx for idx in range(symbol_count) if idx not in exclude]
        if not candidates:
            return near_targets[0]

        weights: List[float] = []
        for candidate in candidates:
            min_distance = min(abs(candidate - target) for target in near_targets)
            # Invert distance (with +1 to avoid division by zero) to weight near misses higher
            weights.append(1.0 / (min_distance + 1.0))

        total_weight = sum(weights)
        if total_weight <= 0:
            return random_module.choice(candidates)

        threshold = random_module.random() * total_weight
        cumulative = 0.0
        for candidate, weight in zip(candidates, weights):
            cumulative += weight
            if cumulative >= threshold:
                return candidate

        return candidates[-1]

    if pattern_type == "all_different" and symbol_count >= 3:
        # Generate three different symbols with weighted near-miss preference
        first = random_module.randint(0, symbol_count - 1)
        second = _weighted_choice({first}, [first])
        third = _weighted_choice({first, second}, [first, second])
        return [first, second, third]
    else:
        # Generate pattern [a, a, b] - first two same, third different
        same_symbol = random_module.randint(0, symbol_count - 1)
        different_symbol = _weighted_choice({same_symbol}, [same_symbol])

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

    card_title = f"[{card.id}] {card.rarity} {card.modifier} {card.base_name}".strip()
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

        if debug_mode:
            # In debug mode, target the requesting user directly
            chat_id = user_id
        else:
            card1_chat_id = card1.chat_id
            card2_chat_id = card2.chat_id

            if not card1_chat_id or not card2_chat_id:
                fallback_chat_id = os.getenv("GROUP_CHAT_ID")
                if fallback_chat_id:
                    logger.warning(
                        "Missing chat_id on one or both cards for trade %s/%s; falling back to GROUP_CHAT_ID",
                        card_id1,
                        card_id2,
                    )
                    chat_id = fallback_chat_id
                else:
                    logger.error(
                        "Missing chat_id on cards %s and %s with no GROUP_CHAT_ID fallback configured",
                        card_id1,
                        card_id2,
                    )
                    raise HTTPException(status_code=500, detail="Card chat not configured")
            else:
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
                chat_id = card1_chat_id

        # Get current user's username from the validated init data
        current_username = user_data.get("username")
        if not current_username:
            logger.error(f"Username not found in init data for user_id {user_id}")
            raise HTTPException(status_code=400, detail="Username not found in init data")

        # Validate trade
        if card1.owner != current_username:
            raise HTTPException(
                status_code=403, detail=f"You do not own card {card1.modifier} {card1.base_name}"
            )

        if card2.owner == current_username:
            raise HTTPException(
                status_code=400, detail=f"You already own card {card2.modifier} {card2.base_name}"
            )

        # Send trade request message with accept/reject buttons
        trade_message = TRADE_REQUEST_MESSAGE.format(
            user1_username=current_username,
            card1_title=f"{card1.modifier} {card1.base_name}",
            user2_username=card2.owner,
            card2_title=f"{card2.modifier} {card2.base_name}",
        )

        # Create inline keyboard with accept/reject buttons
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [
                InlineKeyboardButton("Accept", callback_data=f"trade_accept_{card_id1}_{card_id2}"),
                InlineKeyboardButton("Reject", callback_data=f"trade_reject_{card_id1}_{card_id2}"),
            ]
        ]
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

            # Get thread_id if available
            thread_id = await asyncio.to_thread(database.get_thread_id, str(chat_id))

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

        return SpinsResponse(spins=spins_count, success=True)

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
    if request.symbol_count <= 0:
        raise HTTPException(status_code=400, detail="Symbol count must be positive")

    if request.random_number < 0 or request.random_number >= request.symbol_count:
        raise HTTPException(
            status_code=400,
            detail=f"Random number must be between 0 and {request.symbol_count - 1}",
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
        is_win = random.random() < win_chance
        rarity: Optional[str] = None

        if is_win:
            # All three reels show the same symbol
            winning_symbol = random.randint(0, request.symbol_count - 1)
            results = [winning_symbol, winning_symbol, winning_symbol]
            rarity = _pick_slot_rarity(random)
        else:
            # Generate a dramatic loss pattern (no [a, b, a] near-miss patterns)
            results = _generate_slot_loss_pattern(random, request.symbol_count)

        logger.info(
            f"Slot verification for user {request.user_id} in chat {request.chat_id}: "
            f"win={is_win}, win_chance={win_chance:.3f}, results={results}, rarity={rarity}"
        )

        return SlotVerifyResponse(is_win=is_win, results=results, rarity=rarity)

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
            # Generate card from source
            generated_card = await asyncio.to_thread(
                rolling.generate_card_from_source,
                source_type,
                source_id,
                gemini_util,
                normalized_rarity,
            )

            # Add card to database and assign to winner
            card_id = await asyncio.to_thread(
                database.add_card,
                generated_card.base_name,
                generated_card.modifier,
                generated_card.rarity,
                generated_card.image_b64,
                chat_id,
            )

            await asyncio.to_thread(database.set_card_owner, card_id, username, user_id)

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

    except Exception as exc:
        logger.error("Critical error in slots victory background processing: %s", exc)


# =============================================================================
# CHAT ENDPOINTS
# =============================================================================


@app.get("/chat/{chat_id}/users-characters", response_model=List[ChatUserCharacterSummary])
async def get_chat_users_and_characters_endpoint(
    chat_id: str,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Get all users and characters for a specific chat with their display names and slot icons."""
    try:
        # Get users and characters data from database
        data = await asyncio.to_thread(database.get_chat_users_and_characters, chat_id)

        # Convert to response models and return directly
        return [ChatUserCharacterSummary(**item) for item in data]

    except Exception as e:
        logger.error(f"Error fetching chat users/characters for chat_id {chat_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch chat users and characters")


def run_server():
    """Run the FastAPI server."""
    # Disable reload when running in a thread to avoid signal handler issues
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run_server()
