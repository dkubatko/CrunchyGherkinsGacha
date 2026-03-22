"""
Bot handler registration.

This module contains functions for registering all command and callback
handlers with the Telegram bot application.
"""

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from handlers import (
    # User handlers
    start,
    profile,
    delete_character,
    enroll,
    unenroll,
    # Rolling handlers
    roll,
    handle_claim,
    handle_lock,
    handle_reroll,
    # Card handlers
    refresh,
    handle_refresh_callback,
    equip,
    handle_equip_callback,
    # Aspect handlers (burn, lock, recycle, create)
    burn,
    handle_burn_callback,
    lock_aspect_command,
    handle_lock_aspect_confirm,
    recycle,
    handle_recycle_callback,
    create_unique_aspect,
    handle_create_callback,
    # Collection handlers
    casino,
    balance,
    collection,
    handle_collection_show,
    handle_collection_navigation,
    handle_collection_dismiss,
    stats,
    # Trade handlers
    trade,
    accept_card_trade,
    reject_card_trade,
    accept_aspect_trade,
    reject_aspect_trade,
    # Admin handlers
    spins,
    reload,
    set_thread,
)


def register_handlers(application: Application) -> None:
    """
    Register all command and callback handlers with the application.

    Handlers are organized by domain:
    - User management (start, profile, enroll/unenroll)
    - Collection and casino
    - Card operations (roll, recycle, burn, create, refresh, lock)
    - Trading
    - Admin commands

    Args:
        application: The Telegram bot application instance.
    """
    _register_user_handlers(application)
    _register_collection_handlers(application)
    _register_card_handlers(application)
    _register_trade_handlers(application)
    _register_admin_handlers(application)
    _register_callback_handlers(application)


def _register_user_handlers(application: Application) -> None:
    """Register user management command handlers."""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(
        MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/profile\b"), profile)
    )
    application.add_handler(CommandHandler("delete", delete_character))
    application.add_handler(CommandHandler("enroll", enroll))
    application.add_handler(CommandHandler("unenroll", unenroll))


def _register_collection_handlers(application: Application) -> None:
    """Register collection and casino command handlers."""
    application.add_handler(CommandHandler("casino", casino))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("collection", collection))
    application.add_handler(CommandHandler("stats", stats))


def _register_card_handlers(application: Application) -> None:
    """Register card operation command handlers."""
    application.add_handler(CommandHandler("roll", roll))
    application.add_handler(CommandHandler("recycle", recycle))
    application.add_handler(CommandHandler("burn", burn))
    application.add_handler(CommandHandler("create", create_unique_aspect))
    application.add_handler(CommandHandler("refresh", refresh))
    application.add_handler(CommandHandler("lock", lock_aspect_command))
    application.add_handler(CommandHandler("equip", equip))


def _register_trade_handlers(application: Application) -> None:
    """Register trade command handlers."""
    application.add_handler(CommandHandler("trade", trade))


def _register_admin_handlers(application: Application) -> None:
    """Register admin-only command handlers."""
    application.add_handler(CommandHandler("spins", spins))
    application.add_handler(CommandHandler("reload", reload))
    application.add_handler(CommandHandler("set_thread", set_thread))


def _register_callback_handlers(application: Application) -> None:
    """Register all callback query handlers."""
    # Roll action callbacks (unified for card & aspect via a?<action>_ patterns)
    application.add_handler(CallbackQueryHandler(handle_claim, pattern="^a?claim_"))
    application.add_handler(CallbackQueryHandler(handle_lock, pattern="^a?lock_"))
    application.add_handler(CallbackQueryHandler(handle_reroll, pattern="^a?reroll_"))

    # Aspect burn, lock, recycle callbacks
    application.add_handler(CallbackQueryHandler(handle_burn_callback, pattern="^aburn_"))
    application.add_handler(
        CallbackQueryHandler(handle_lock_aspect_confirm, pattern="^alockaspect_")
    )
    application.add_handler(CallbackQueryHandler(handle_recycle_callback, pattern="^arecycle_"))
    application.add_handler(CallbackQueryHandler(handle_create_callback, pattern="^create_"))
    application.add_handler(CallbackQueryHandler(handle_refresh_callback, pattern="^refresh_"))
    application.add_handler(CallbackQueryHandler(handle_equip_callback, pattern="^equip_"))

    # Collection navigation callbacks
    application.add_handler(
        CallbackQueryHandler(handle_collection_show, pattern="^collection_show_")
    )
    application.add_handler(
        CallbackQueryHandler(handle_collection_dismiss, pattern="^collection_dismiss_")
    )
    application.add_handler(
        CallbackQueryHandler(handle_collection_navigation, pattern="^collection_(prev|next|close)_")
    )

    # Card trade callbacks
    application.add_handler(CallbackQueryHandler(accept_card_trade, pattern="^card_trade_accept_"))
    application.add_handler(CallbackQueryHandler(reject_card_trade, pattern="^card_trade_reject_"))
    # Aspect trade callbacks
    application.add_handler(
        CallbackQueryHandler(accept_aspect_trade, pattern="^aspect_trade_accept_")
    )
    application.add_handler(
        CallbackQueryHandler(reject_aspect_trade, pattern="^aspect_trade_reject_")
    )
