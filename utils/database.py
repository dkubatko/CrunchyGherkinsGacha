import sqlite3
import os
import datetime

DB_PATH = "data/cards.db"


def connect():
    """Connect to the SQLite database."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    return conn


def create_tables():
    """Create the tables if they don't exist."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            base_name TEXT NOT NULL,
            modifier TEXT NOT NULL,
            rarity TEXT NOT NULL,
            owner TEXT,
            image_b64 TEXT
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_rolls (
            user_id INTEGER PRIMARY KEY,
            last_roll_date TEXT NOT NULL
        )
    """
    )
    conn.commit()
    conn.close()


def add_card(base_name, modifier, rarity, image_b64):
    """Add a new card to the database."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO cards (base_name, modifier, rarity, image_b64)
        VALUES (?, ?, ?, ?)
    """,
        (base_name, modifier, rarity, image_b64),
    )
    card_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return card_id


def claim_card(card_id, owner):
    """Claim a card for a user."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE cards SET owner = ? WHERE id = ? AND owner IS NULL", (owner, card_id))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def get_user_collection(username):
    """Get all cards owned by a user."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM cards WHERE owner = ? ORDER BY CASE rarity WHEN 'Legendary' THEN 1 WHEN 'Epic' THEN 2 WHEN 'Rare' THEN 3 ELSE 4 END, base_name, modifier",
        (username,),
    )
    cards = cursor.fetchall()
    conn.close()
    return cards


def get_card(card_id):
    """Get a card by its ID."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
    card = cursor.fetchone()
    conn.close()
    return card


def get_total_cards_count():
    """Get the total number of cards ever generated."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cards")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_user_stats(username):
    """Get card statistics for a user."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cards WHERE owner = ?", (username,))
    owned_count = cursor.fetchone()[0]

    rarities = ["Legendary", "Epic", "Rare", "Common"]
    rarity_counts = {}
    for rarity in rarities:
        cursor.execute(
            "SELECT COUNT(*) FROM cards WHERE owner = ? AND rarity = ?", (username, rarity)
        )
        rarity_counts[rarity] = cursor.fetchone()[0]

    total_count = get_total_cards_count()
    conn.close()

    return {"owned": owned_count, "total": total_count, "rarities": rarity_counts}


def can_roll(user_id):
    """Check if a user can roll today."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT last_roll_date FROM user_rolls WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        last_roll_date = datetime.datetime.strptime(result[0], "%Y-%m-%d").date()
        if last_roll_date == datetime.date.today():
            return False
    return True


def record_roll(user_id):
    """Record a user's roll for today."""
    conn = connect()
    cursor = conn.cursor()
    today = datetime.date.today().isoformat()
    cursor.execute(
        "INSERT OR REPLACE INTO user_rolls (user_id, last_roll_date) VALUES (?, ?)",
        (user_id, today),
    )
    conn.commit()
    conn.close()


create_tables()
