import asyncio
import os
import sys
import logging
from typing import List, Optional

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
from utils.encoder import EncoderUtil
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

# Initialize encoder utility
encoder_util = EncoderUtil()

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

    # Extract token from "Bearer <token>" format
    token = None
    if authorization.startswith("Bearer "):
        token = authorization[7:]  # Remove "Bearer " prefix
    else:
        token = authorization  # Use as-is if no Bearer prefix

    # Decode and validate the token
    user_data = encoder_util.decode_data(token)
    if not user_data:
        logger.warning(f"Invalid token provided for /cards/all")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    cards = await asyncio.to_thread(database.get_all_cards)
    return [APICard(**card.__dict__) for card in cards]


@app.get("/cards/{username}", response_model=List[APICard])
async def get_user_collection(
    username: str, authorization: Optional[str] = Header(None, alias="Authorization")
):
    """Get all cards owned by a user.

    This endpoint requires authentication via Authorization header with encoded user data.
    """

    # Check if authorization header is provided
    if not authorization:
        logger.warning(f"No authorization header provided for username: {username}")
        raise HTTPException(status_code=401, detail="Authorization header required")

    # Extract token from "Bearer <token>" format
    token = None
    if authorization.startswith("Bearer "):
        token = authorization[7:]  # Remove "Bearer " prefix
    else:
        token = authorization  # Use as-is if no Bearer prefix

    # Decode and validate the token
    user_data = encoder_util.decode_data(token)
    if not user_data:
        logger.warning(f"Invalid token provided for username: {username}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

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

    token = None
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization

    user_data = encoder_util.decode_data(token)
    if not user_data:
        logger.warning(f"Invalid token provided for card_id: {card_id}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

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

    # Extract token from "Bearer <token>" format
    token = None
    if authorization.startswith("Bearer "):
        token = authorization[7:]  # Remove "Bearer " prefix
    else:
        token = authorization  # Use as-is if no Bearer prefix

    # Decode and validate the token
    user_data = encoder_util.decode_data(token)
    if not user_data:
        logger.warning(f"Invalid token provided for trade {card_id1}/{card_id2}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Get user_id and chat_id from decoded data
    user_id = user_data.get("user_id")
    chat_id = user_data.get("chat_id")

    if not user_id or not chat_id:
        logger.warning(f"Missing user_id or chat_id in token for trade {card_id1}/{card_id2}")
        raise HTTPException(status_code=400, detail="Invalid user data in token")

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

        # Get current user's username from the token
        current_username = user_data.get("username")
        if not current_username:
            logger.error(f"Username not found in token for user_id {user_id}")
            raise HTTPException(status_code=400, detail="Username not found in token")

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
