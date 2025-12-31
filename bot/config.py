"""
Shared configuration and utilities for bot handlers.

This module centralizes all configuration, environment variables, and shared utilities
that are used across different handler modules. It initializes the database, decorators,
and other utilities on import.
"""

import logging
import os
import sys

from dotenv import load_dotenv

from utils import database, decorators, gemini, minesweeper
from utils.logging_utils import configure_logging

# Load environment variables
load_dotenv()

# Determine debug mode
DEBUG_MODE = "--debug" in sys.argv or os.getenv("DEBUG_MODE") == "1"

# Configure logging
configure_logging(debug=DEBUG_MODE)
logger = logging.getLogger(__name__)

# Maximum retries for image generation
MAX_BOT_IMAGE_RETRIES = 2

# Load environment-specific variables
if DEBUG_MODE:
    TELEGRAM_TOKEN = os.getenv("DEBUG_TELEGRAM_AUTH_TOKEN")
    ADMIN_USERNAME = os.getenv("DEBUG_BOT_ADMIN")
    MINIAPP_URL_ENV = os.getenv("DEBUG_MINIAPP_URL")
else:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_AUTH_TOKEN")
    ADMIN_USERNAME = os.getenv("BOT_ADMIN")
    MINIAPP_URL_ENV = os.getenv("MINIAPP_URL")

# Google AI configuration
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
IMAGE_GEN_MODEL = os.getenv("IMAGE_GEN_MODEL")

# Database configuration
DB_POOL_SIZE = int(os.getenv("DB_CONNECTION_POOL_SIZE", "6"))
DB_TIMEOUT_SECONDS = int(os.getenv("DB_CONNECTION_TIMEOUT_SECONDS", "30"))
DB_BUSY_TIMEOUT_MS = int(os.getenv("DB_BUSY_TIMEOUT_MS", "5000"))


def initialize_bot_utilities():
    """Initialize all bot utilities. Should be called once at startup."""
    database.initialize_database(DB_POOL_SIZE, DB_TIMEOUT_SECONDS, DB_BUSY_TIMEOUT_MS)
    decorators.set_admin_username(ADMIN_USERNAME)
    minesweeper.set_debug_mode(DEBUG_MODE)

    # Initialize achievement system
    from utils.achievements import init_achievements, ensure_achievements_registered

    init_achievements()
    ensure_achievements_registered()

    logger.info("Bot utilities initialized")


# Initialize Gemini utility (lazy - creates instance but doesn't connect until used)
gemini_util = gemini.GeminiUtil(GOOGLE_API_KEY, IMAGE_GEN_MODEL)
