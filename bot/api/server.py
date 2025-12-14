"""
FastAPI server for the Telegram Mini App API.

This is the main entry point for the API server. It sets up the FastAPI application,
configures middleware, and includes all routers from the modular router files.
"""

import logging
import uvicorn

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import DEBUG_MODE
from api.routers import (
    cards_router,
    chat_router,
    minesweeper_router,
    slots_router,
    trade_router,
    user_router,
)

logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="Crunchy Gherkins Gacha Bot API",
    description="API for the Telegram Mini App",
    version="1.0.0",
)

# CORS configuration
allowed_origins = [
    "https://app.crunchygherkins.com",
    "http://localhost:5173",  # For local development
]

if DEBUG_MODE:
    allowed_origins.extend(
        [
            "http://192.168.1.142:5173",  # Local IP for mobile testing
            "https://192.168.1.142:5173",  # HTTPS version if needed
        ]
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Include all routers
app.include_router(cards_router)
app.include_router(trade_router)
app.include_router(user_router)
app.include_router(slots_router)
app.include_router(minesweeper_router)
app.include_router(chat_router)


def run_server():
    """Run the FastAPI server."""
    if DEBUG_MODE:
        logger.info("🧪 Running API server in DEBUG mode with test environment endpoints")
    else:
        logger.info("🚀 Running API server in PRODUCTION mode with local Telegram Bot API server")

    logger.info("🌐 Starting FastAPI server on http://0.0.0.0:8000")
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run_server()
