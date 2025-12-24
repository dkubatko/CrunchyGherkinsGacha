"""
Bot core package.

This module exports the core components for setting up and running the Telegram bot.
Components are organized by responsibility:
- application: Application factory and creation
- handlers: Handler registration

Configuration is centralized in handlers/config.py.
"""

from core.application import create_application
from core.handlers import register_handlers

__all__ = [
    "create_application",
    "register_handlers",
]
