"""
API Routers package.

This module exports all API routers for use in the main FastAPI application.
"""

from api.routers.cards import router as cards_router
from api.routers.chat import router as chat_router
from api.routers.minesweeper import router as minesweeper_router
from api.routers.slots import router as slots_router
from api.routers.trade import router as trade_router
from api.routers.user import router as user_router

__all__ = [
    "cards_router",
    "chat_router",
    "minesweeper_router",
    "slots_router",
    "trade_router",
    "user_router",
]
