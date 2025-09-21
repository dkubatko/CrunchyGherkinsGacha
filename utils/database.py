import sqlite3
import os
import datetime
import logging
import base64

logger = logging.getLogger(__name__)

DB_PATH = "data/cards.db"


class Card:
    def __init__(
        self, id, base_name, modifier, rarity, owner, image_b64, attempted_by, file_id=None
    ):
        self.id = id
        self.base_name = base_name
        self.modifier = modifier
        self.rarity = rarity
        self.owner = owner
        self.image_b64 = image_b64
        self.attempted_by = attempted_by
        self.file_id = file_id

    def title(self):
        """Return the card's full title."""
        return f"{self.rarity} {self.modifier} {self.base_name}"

    def get_media(self):
        """Return file_id if available, otherwise return decoded base64 image data."""
        if self.file_id:
            return self.file_id
        return base64.b64decode(self.image_b64)


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
            image_b64 TEXT,
            attempted_by TEXT DEFAULT '',
            file_id TEXT
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_rolls (
            user_id INTEGER PRIMARY KEY,
            last_roll_timestamp TEXT NOT NULL
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

    # Check if card is already claimed
    cursor.execute("SELECT owner, attempted_by FROM cards WHERE id = ?", (card_id,))
    result = cursor.fetchone()

    if result and result[0] is not None:
        # Card already claimed, add to attempted_by list
        attempted_by = result[1] or ""
        attempted_list = [u.strip() for u in attempted_by.split(",") if u.strip()]
        if owner not in attempted_list:
            attempted_list.append(owner)
            new_attempted_by = ", ".join(attempted_list)
            cursor.execute(
                "UPDATE cards SET attempted_by = ? WHERE id = ?", (new_attempted_by, card_id)
            )
            conn.commit()
        conn.close()
        return False
    else:
        # Claim the card
        cursor.execute(
            "UPDATE cards SET owner = ? WHERE id = ? AND owner IS NULL", (owner, card_id)
        )
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
    cards = [Card(*row) for row in cursor.fetchall()]
    conn.close()
    return cards


def get_card(card_id):
    """Get a card by its ID."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
    card_data = cursor.fetchone()
    conn.close()
    return Card(*card_data) if card_data else None


def get_total_cards_count():
    """Get the total number of cards ever generated."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM cards WHERE owner IS NOT NULL")
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


def get_all_users_with_cards():
    """Get all unique users who have claimed cards."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT owner FROM cards WHERE owner IS NOT NULL ORDER BY owner")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users


def get_last_roll_time(user_id):
    """Get the last roll timestamp for a user."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT last_roll_timestamp FROM user_rolls WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return datetime.datetime.fromisoformat(result[0])
    return None


def can_roll(user_id):
    """Check if a user can roll (24 hours since last roll)."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT last_roll_timestamp FROM user_rolls WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        last_roll_time = datetime.datetime.fromisoformat(result[0])
        time_since_last_roll = datetime.datetime.now() - last_roll_time
        if time_since_last_roll.total_seconds() < 24 * 60 * 60:  # 24 hours in seconds
            return False
    return True


def record_roll(user_id):
    """Record a user's roll timestamp."""
    conn = connect()
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cursor.execute(
        "INSERT OR REPLACE INTO user_rolls (user_id, last_roll_timestamp) VALUES (?, ?)",
        (user_id, now),
    )
    conn.commit()
    conn.close()


def swap_card_owners(card_id1, card_id2):
    """Swap the owners of two cards."""
    conn = connect()
    cursor = conn.cursor()
    try:
        # Get current owners
        cursor.execute("SELECT owner FROM cards WHERE id = ?", (card_id1,))
        owner1 = cursor.fetchone()[0]

        cursor.execute("SELECT owner FROM cards WHERE id = ?", (card_id2,))
        owner2 = cursor.fetchone()[0]

        # Swap owners
        cursor.execute("UPDATE cards SET owner = ? WHERE id = ?", (owner2, card_id1))
        cursor.execute("UPDATE cards SET owner = ? WHERE id = ?", (owner1, card_id2))

        conn.commit()
        return True
    except sqlite3.Error:
        conn.rollback()
        return False
    finally:
        conn.close()


def update_card_file_id(card_id, file_id):
    """Update the Telegram file_id for a card."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE cards SET file_id = ? WHERE id = ?", (file_id, card_id))
    conn.commit()
    conn.close()
    logger.info(f"Updated file_id for card {card_id}: {file_id}")


def clear_all_file_ids():
    """Clear all file_ids from all cards (set to NULL)."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE cards SET file_id = NULL")
    affected_rows = cursor.rowcount
    conn.commit()
    conn.close()
    logger.info(f"Cleared file_ids for {affected_rows} cards")
    return affected_rows


create_tables()
