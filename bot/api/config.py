"""
Shared configuration and initialization for the API server.

This module provides centralized access to environment variables, database initialization,
and shared utilities that are used across all API routers.
"""

import os
import sys
import logging
from typing import List, Tuple

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to sys.path to allow importing from bot
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils import database, gemini, minesweeper
from utils.logging_utils import configure_logging
from settings.constants import RARITIES

# Debug mode detection
DEBUG_MODE = "--debug" in sys.argv or os.getenv("DEBUG_MODE") == "1"

# No generation mode (only effective with DEBUG_MODE)
NO_GENERATION = ("--no-generation" in sys.argv or os.getenv("NO_GENERATION") == "1") and DEBUG_MODE

# Configure logging
configure_logging(debug=DEBUG_MODE)

logger = logging.getLogger(__name__)

# Environment-based configuration
if DEBUG_MODE:
    TELEGRAM_TOKEN = os.getenv("DEBUG_TELEGRAM_AUTH_TOKEN")
    MINIAPP_URL = os.getenv("DEBUG_MINIAPP_URL")
else:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_AUTH_TOKEN")
    MINIAPP_URL = os.getenv("MINIAPP_URL")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
IMAGE_GEN_MODEL = os.getenv("IMAGE_GEN_MODEL")

# Database configuration
DB_POOL_SIZE = int(os.getenv("DB_CONNECTION_POOL_SIZE", "6"))
DB_TIMEOUT_SECONDS = int(os.getenv("DB_CONNECTION_TIMEOUT_SECONDS", "30"))
DB_BUSY_TIMEOUT_MS = int(os.getenv("DB_BUSY_TIMEOUT_MS", "5000"))

# Initialize utilities with configuration
database.initialize_database(DB_POOL_SIZE, DB_TIMEOUT_SECONDS, DB_BUSY_TIMEOUT_MS)
minesweeper.set_debug_mode(DEBUG_MODE)

# Gemini utility for image generation
gemini_util = gemini.GeminiUtil(GOOGLE_API_KEY, IMAGE_GEN_MODEL)

# Maximum retries for slot victory image generation
MAX_SLOT_VICTORY_IMAGE_RETRIES = 2

# Rarity weight configuration for slot machine
_RARITY_WEIGHT_PAIRS: List[Tuple[str, int]] = [
    (name, int(details.get("weight", 0)))
    for name, details in RARITIES.items()
    if isinstance(details, dict) and int(details.get("weight", 0)) > 0
]
_RARITY_TOTAL_WEIGHT = sum(weight for _, weight in _RARITY_WEIGHT_PAIRS)


def get_rarity_weight_pairs() -> List[Tuple[str, int]]:
    """Get the list of rarity weight pairs."""
    return _RARITY_WEIGHT_PAIRS


def get_rarity_total_weight() -> int:
    """Get the total weight of all rarities."""
    return _RARITY_TOTAL_WEIGHT


def create_bot_instance():
    """
    Create a Telegram Bot instance with appropriate configuration.

    In debug mode: Uses Telegram's test environment endpoints.
    In production: Uses local Telegram Bot API server with local_mode=True.

    Returns:
        Bot: Configured Telegram Bot instance

    Raises:
        HTTPException: If TELEGRAM_TOKEN is not available
    """
    from telegram import Bot
    from fastapi import HTTPException

    if not TELEGRAM_TOKEN:
        logger.error("Bot token not available for bot instance creation")
        raise HTTPException(status_code=503, detail="Bot service unavailable")

    if DEBUG_MODE:
        bot = Bot(token=TELEGRAM_TOKEN)
        bot._base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/test"
        bot._base_file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/test"
        return bot
    else:
        # Use local Telegram Bot API server in production
        api_base_url = "http://localhost:8081"
        return Bot(
            token=TELEGRAM_TOKEN,
            base_url=f"{api_base_url}/bot",
            base_file_url=f"{api_base_url}/file/bot",
            local_mode=True,
        )
