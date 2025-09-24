import asyncio
import os
import sys
from typing import List

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add project root to sys.path to allow importing from bot
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils import database
from utils.database import Card as APICard

app = FastAPI()

DEBUG_MODE = "--debug" in sys.argv or os.getenv("DEBUG", "").lower() in ("true", "1", "yes")

# CORS configuration
allowed_origins = [
    "https://app.crunchygherkins.com",
    "http://localhost:5173",  # For local development
]

if DEBUG_MODE:
    allowed_origins.extend(
        [
            "http://192.168.1.200:5173",  # Local IP for mobile testing
            "https://192.168.1.200:5173",  # HTTPS version if needed
        ]
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.get("/cards/{username}", response_model=List[APICard])
async def get_user_collection_api(username: str):
    """Get all cards owned by a user."""
    cards = await asyncio.to_thread(database.get_user_collection, username)
    return [APICard(**card.__dict__) for card in cards]


def run_server():
    """Run the FastAPI server."""
    # Disable reload when running in a thread to avoid signal handler issues
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run_server()
