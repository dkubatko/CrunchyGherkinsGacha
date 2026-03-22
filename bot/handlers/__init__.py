"""
Bot handlers package.

This module exports all command and callback handlers for use in the main bot application.
Handlers are organized by domain:
- user: Registration, profile, enrollment
- rolling: Roll, reroll cards
- cards: Refresh, equip
- aspects: Burn, lock, recycle, create unique aspects
- collection: Collection view, balance, stats, casino
- trade: Trade initiation, acceptance, rejection
- admin: Admin-only commands (spins, reload, set_thread)
"""

# User handlers
from handlers.user import (
    start,
    profile,
    delete_character,
    enroll,
    unenroll,
)

# Rolling handlers
from handlers.rolling import (
    roll,
    handle_claim,
    handle_lock,
    handle_reroll,
)

# Card handlers
from handlers.cards import (
    refresh,
    handle_refresh_callback,
    equip,
    handle_equip_callback,
)

# Aspect handlers (burn, lock, recycle, create)
from handlers.aspects import (
    burn,
    handle_burn_callback,
    lock_aspect_command,
    handle_lock_aspect_confirm,
    recycle,
    handle_recycle_callback,
    create_unique_aspect,
    handle_create_callback,
)

# Collection handlers
from handlers.collection import (
    casino,
    balance,
    collection,
    handle_collection_show,
    handle_collection_navigation,
    handle_collection_dismiss,
    stats,
)

# Trade handlers
from handlers.trade import (
    trade,
    accept_trade,
    reject_trade,
)

# Admin handlers
from handlers.admin import (
    spins,
    reload,
    set_thread,
)

# Config and helpers
from config import (
    DEBUG_MODE,
    TELEGRAM_TOKEN,
    ADMIN_USERNAME,
    MINIAPP_URL_ENV,
    initialize_bot_utilities,
)

__all__ = [
    # User handlers
    "start",
    "profile",
    "delete_character",
    "enroll",
    "unenroll",
    # Rolling handlers
    "roll",
    "handle_claim",
    "handle_lock",
    "handle_reroll",
    # Card handlers
    "refresh",
    "handle_refresh_callback",
    "equip",
    "handle_equip_callback",
    # Aspect handlers (burn, lock, recycle, create)
    "burn",
    "handle_burn_callback",
    "lock_aspect_command",
    "handle_lock_aspect_confirm",
    "recycle",
    "handle_recycle_callback",
    "create_unique_aspect",
    "handle_create_callback",
    # Collection handlers
    "casino",
    "balance",
    "collection",
    "handle_collection_show",
    "handle_collection_navigation",
    "handle_collection_dismiss",
    "stats",
    # Trade handlers
    "trade",
    "accept_trade",
    "reject_trade",
    # Admin handlers
    "spins",
    "reload",
    "set_thread",
    # Config
    "DEBUG_MODE",
    "TELEGRAM_TOKEN",
    "ADMIN_USERNAME",
    "MINIAPP_URL_ENV",
    "initialize_bot_utilities",
]
