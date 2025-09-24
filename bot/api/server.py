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

# Initialize logger
logger = logging.getLogger(__name__)

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


def run_server():
    """Run the FastAPI server."""
    # Disable reload when running in a thread to avoid signal handler issues
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run_server()
