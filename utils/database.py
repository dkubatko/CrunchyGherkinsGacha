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
            image_b64 TEXT,
            attempted_by TEXT DEFAULT ''
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

    # Migrate existing data if needed
    try:
        # Check if old column exists
        cursor.execute("PRAGMA table_info(user_rolls)")
        columns = [column[1] for column in cursor.fetchall()]
        if "last_roll_date" in columns and "last_roll_timestamp" not in columns:
            # Need to migrate from date to timestamp
            cursor.execute("ALTER TABLE user_rolls ADD COLUMN last_roll_timestamp TEXT")

            # Convert existing dates to timestamps (set to start of day)
            cursor.execute(
                "SELECT user_id, last_roll_date FROM user_rolls WHERE last_roll_date IS NOT NULL"
            )
            rows = cursor.fetchall()
            for user_id, date_str in rows:
                # Convert date to timestamp at start of day
                date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                timestamp = date_obj.isoformat()
                cursor.execute(
                    "UPDATE user_rolls SET last_roll_timestamp = ? WHERE user_id = ?",
                    (timestamp, user_id),
                )

            # Drop the old column by recreating the table
            cursor.execute(
                "CREATE TABLE user_rolls_new (user_id INTEGER PRIMARY KEY, last_roll_timestamp TEXT NOT NULL)"
            )
            cursor.execute(
                "INSERT INTO user_rolls_new SELECT user_id, last_roll_timestamp FROM user_rolls"
            )
            cursor.execute("DROP TABLE user_rolls")
            cursor.execute("ALTER TABLE user_rolls_new RENAME TO user_rolls")
    except Exception as e:
        # If migration fails, just continue - the new table structure will be used
        pass

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


create_tables()
