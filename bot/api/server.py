"""
FastAPI server for the Telegram Mini App API.

This is the main entry point for the API server. It sets up the FastAPI application,
configures middleware, and includes all routers from the modular router files.
"""

import logging
import traceback
import uvicorn

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from api.config import DEBUG_MODE
from api.limiter import limiter
from api.routers import (
    cards_router,
    chat_router,
    downloads_router,
    minesweeper_router,
    rtb_router,
    slots_router,
    trade_router,
    user_router,
    admin_auth_router,
    admin_sets_router,
    admin_modifiers_router,
)

logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="Crunchy Gherkins Gacha Bot API",
    description="API for the Telegram Mini App",
    version="1.0.0",
)

# Register limiter with app state for access in routers
app.state.limiter = limiter


# Rate limit exceeded handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Log full tracebacks for unhandled exceptions."""
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}:\n" f"{traceback.format_exc()}"
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# CORS configuration
if DEBUG_MODE:
    # Allow any origin in debug mode for easier local development
    allowed_origins = ["*"]
else:
    allowed_origins = [
        "https://app.crunchygherkins.com",
        "https://admin.crunchygherkins.com",
        "http://localhost:5173",
        "http://localhost:5174",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=not DEBUG_MODE,  # credentials not supported with wildcard origin
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Include all routers
app.include_router(cards_router)
app.include_router(downloads_router)
app.include_router(trade_router)
app.include_router(user_router)
app.include_router(slots_router)
app.include_router(minesweeper_router)
app.include_router(rtb_router)
app.include_router(chat_router)
app.include_router(admin_auth_router)
app.include_router(admin_sets_router)
app.include_router(admin_modifiers_router)


@app.on_event("startup")
async def startup_event():
    """Initialize services on API startup."""
    from utils.achievements import init_achievements, ensure_achievements_registered
    from utils.modifiers import init_modifier_count_listener

    init_achievements()
    ensure_achievements_registered()
    logger.info("Achievement system initialized for API")

    init_modifier_count_listener()
    logger.info("Modifier count listener initialized for API")


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
