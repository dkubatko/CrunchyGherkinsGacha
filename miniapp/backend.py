from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
import base64
from pydantic import BaseModel
from typing import List

app = FastAPI()

# CORS configuration for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.crunchygherkins.com",
        "http://localhost:5173",  # For local development
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

DB_PATH = "/usr/local/gacha/database/cards.db"


class Card(BaseModel):
    id: int
    base_name: str
    modifier: str
    rarity: str
    owner: str | None
    image_b64: str
    attempted_by: str
    file_id: str | None
    created_at: str | None

    def title(self):
        """Return the card's full title."""
        return f"{self.rarity} {self.modifier} {self.base_name}"


def connect():
    """Connect to the SQLite database."""
    # The database directory might not exist if running outside the bot's environment
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/cards/{username}", response_model=List[Card])
def get_user_collection(username: str):
    """Get all cards owned by a user."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM cards WHERE owner = ? ORDER BY CASE rarity WHEN 'Legendary' THEN 1 WHEN 'Epic' THEN 2 WHEN 'Rare' THEN 3 ELSE 4 END, base_name, modifier",
        (username,),
    )
    cards = [Card(**row) for row in cursor.fetchall()]
    conn.close()
    return cards
