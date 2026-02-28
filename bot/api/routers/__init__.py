"""
API Routers package.

This module exports all API routers for use in the main FastAPI application.
"""

from api.routers.cards import router as cards_router
from api.routers.chat import router as chat_router
from api.routers.downloads import router as downloads_router
from api.routers.minesweeper import router as minesweeper_router
from api.routers.rtb import router as rtb_router
from api.routers.slots import router as slots_router
from api.routers.trade import router as trade_router
from api.routers.user import router as user_router
from api.routers.admin_auth import router as admin_auth_router
from api.routers.admin_sets import router as admin_sets_router
from api.routers.admin_modifiers import router as admin_modifiers_router

__all__ = [
    "cards_router",
    "chat_router",
    "downloads_router",
    "minesweeper_router",
    "rtb_router",
    "slots_router",
    "trade_router",
    "user_router",
    "admin_auth_router",
    "admin_sets_router",
    "admin_modifiers_router",
]
