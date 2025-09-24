import asyncio
import os
import sys
import logging
import hmac
import hashlib
import urllib.parse
from typing import List, Optional, Dict, Any

import uvicorn
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to sys.path to allow importing from bot
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils import database
from utils.database import Card as APICard
from settings.constants import TRADE_REQUEST_MESSAGE

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


@app.get("/cards/all", response_model=List[APICard])
async def get_all_cards_endpoint(
    authorization: Optional[str] = Header(None, alias="Authorization")
):
    """Get all cards that have been claimed."""

    # Check if authorization header is provided
    if not authorization:
        logger.warning(f"No authorization header provided for /cards/all")
        raise HTTPException(status_code=401, detail="Authorization header required")

    # Extract init data from header
    init_data = extract_init_data_from_header(authorization)
    if not init_data:
        logger.warning(f"No init data found in authorization header for /cards/all")
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    # Validate Telegram init data
    validated_data = validate_telegram_init_data(init_data)
    if not validated_data or not validated_data.get("user"):
        logger.warning(f"Invalid Telegram init data provided for /cards/all")
        raise HTTPException(status_code=401, detail="Invalid or expired Telegram data")

    cards = await asyncio.to_thread(database.get_all_cards)
    return [APICard(**card.__dict__) for card in cards]


@app.get("/cards/{username}", response_model=List[APICard])
async def get_user_collection(
    username: str, authorization: Optional[str] = Header(None, alias="Authorization")
):
    """Get all cards owned by a user.

    This endpoint requires authentication via Authorization header with Telegram WebApp initData.
    """

    # Check if authorization header is provided
    if not authorization:
        logger.warning(f"No authorization header provided for username: {username}")
        raise HTTPException(status_code=401, detail="Authorization header required")

    # Extract init data from header
    init_data = extract_init_data_from_header(authorization)
    if not init_data:
        logger.warning(f"No init data found in authorization header for username: {username}")
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    # Validate Telegram init data
    validated_data = validate_telegram_init_data(init_data)
    if not validated_data or not validated_data.get("user"):
        logger.warning(f"Invalid Telegram init data provided for username: {username}")
        raise HTTPException(status_code=401, detail="Invalid or expired Telegram data")

    cards = await asyncio.to_thread(database.get_user_collection, username)
    return [APICard(**card.__dict__) for card in cards]


@app.get("/cards/image/{card_id}", response_model=str)
async def get_card_image_route(
    card_id: int, authorization: Optional[str] = Header(None, alias="Authorization")
):
    """Get the base64 encoded image for a card."""
    if not authorization:
        logger.warning(f"No authorization header provided for card_id: {card_id}")
        raise HTTPException(status_code=401, detail="Authorization header required")

    # Extract init data from header
    init_data = extract_init_data_from_header(authorization)
    if not init_data:
        logger.warning(f"No init data found in authorization header for card_id: {card_id}")
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    # Validate Telegram init data
    validated_data = validate_telegram_init_data(init_data)
    if not validated_data or not validated_data.get("user"):
        logger.warning(f"Invalid Telegram init data provided for card_id: {card_id}")
        raise HTTPException(status_code=401, detail="Invalid or expired Telegram data")

    image_b64 = await asyncio.to_thread(database.get_card_image, card_id)
    if not image_b64:
        raise HTTPException(status_code=404, detail="Image not found")
    return image_b64


@app.post("/trade/{card_id1}/{card_id2}")
async def execute_trade(
    card_id1: int, card_id2: int, authorization: Optional[str] = Header(None, alias="Authorization")
):
    """Execute a card trade between two cards."""
    global bot_token

    # Check if authorization header is provided
    if not authorization:
        logger.warning(f"No authorization header provided for trade {card_id1}/{card_id2}")
        raise HTTPException(status_code=401, detail="Authorization header required")

    # Extract init data from header
    init_data = extract_init_data_from_header(authorization)
    if not init_data:
        logger.warning(
            f"No init data found in authorization header for trade {card_id1}/{card_id2}"
        )
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    # Validate Telegram init data
    validated_data = validate_telegram_init_data(init_data)
    if not validated_data or not validated_data.get("user"):
        logger.warning(f"Invalid Telegram init data provided for trade {card_id1}/{card_id2}")
        raise HTTPException(status_code=401, detail="Invalid or expired Telegram data")

    # Get user data from validated init data
    user_data = validated_data["user"]
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

            # Send message using the new bot instance
            await bot.send_message(
                chat_id=chat_id, text=trade_message, parse_mode="HTML", reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send trade request message to chat {chat_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to send trade request")

        return {"success": True, "message": "Trade request sent successfully"}

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Unexpected error in trade endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def run_server():
    """Run the FastAPI server."""
    # Disable reload when running in a thread to avoid signal handler issues
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run_server()
