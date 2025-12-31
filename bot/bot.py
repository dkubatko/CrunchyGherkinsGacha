"""
Telegram Bot main entry point.

This is the main entry point for the Telegram bot. It sets up the application,
configures handlers, and starts the bot polling loop.

The bot is organized into modular components:
- core/config: Configuration and environment settings
- core/application: Application factory
- core/handlers: Handler registration
- handlers/: Individual handler implementations by domain
"""

from handlers import initialize_bot_utilities
from core import create_application, register_handlers


def main() -> None:
    """Start the bot."""
    # Initialize utilities (database, decorators, etc.)
    initialize_bot_utilities()

    # Create and configure the application
    application = create_application()

    # Register all handlers
    register_handlers(application)

    # Start polling
    application.run_polling()


if __name__ == "__main__":
    main()
