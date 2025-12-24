"""
Bot application factory.

This module contains the factory function for creating and configuring
the Telegram bot application with the appropriate API endpoints.
"""

import logging

from telegram.ext import Application

from config import DEBUG_MODE, TELEGRAM_TOKEN

logger = logging.getLogger(__name__)


def create_application() -> Application:
    """
    Create and configure the Telegram bot application.

    In debug mode, uses the Telegram test environment endpoints.
    In production mode, uses a local Telegram Bot API server.

    Returns:
        Application: Configured Telegram bot application instance.
    """
    if DEBUG_MODE:
        # Use test environment endpoints when in debug mode
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .base_url("https://api.telegram.org/bot")
            .base_file_url("https://api.telegram.org/file/bot")
            .concurrent_updates(True)
            .build()
        )
        # Override the bot's base_url to include /test/ for test environment
        application.bot._base_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/test"
        application.bot._base_file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/test"
        logger.info("🧪 Running in DEBUG mode with test environment endpoints")
        logger.info(f"🔗 API Base URL: {application.bot._base_url}")
    else:
        # Use local Telegram Bot API server in production
        api_base_url = "http://localhost:8081"
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .base_url(f"{api_base_url}/bot")
            .base_file_url(f"{api_base_url}/file/bot")
            .local_mode(True)
            .concurrent_updates(True)
            .build()
        )
        logger.info("🚀 Running in PRODUCTION mode with local Telegram Bot API server")
        logger.info(f"🔗 API Base URL: {api_base_url}")

    return application
