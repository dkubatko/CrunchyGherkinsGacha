import base64
import datetime
import logging
import os
import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any

from alembic import command
from alembic.config import Config
from pydantic import BaseModel

from settings.constants import DB_PATH

logger = logging.getLogger(__name__)
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
ALEMBIC_INI_PATH = os.path.join(PROJECT_ROOT, "alembic.ini")
ALEMBIC_SCRIPT_LOCATION = os.path.join(PROJECT_ROOT, "alembic")
INITIAL_ALEMBIC_REVISION = "20240924_0001"


class User(BaseModel):
    user_id: int
    username: str
    display_name: Optional[str]
    profile_imageb64: Optional[str]


class Card(BaseModel):
    id: int
    base_name: str
    modifier: str
    rarity: str
    owner: Optional[str]
    user_id: Optional[int]
    attempted_by: str
    file_id: Optional[str]
    chat_id: Optional[str]
    created_at: Optional[str]


class CardWithImage(Card):
    image_b64: str

    def title(self):
        """Return the card's full title."""
        return f"{self.rarity} {self.modifier} {self.base_name}"

    def get_media(self):
        """Return file_id if available, otherwise return decoded base64 image data."""
        if self.file_id:
            return self.file_id
        return base64.b64decode(self.image_b64)


class Claim(BaseModel):
    user_id: int
    chat_id: str
    balance: int


class ClaimStatus(Enum):
    SUCCESS = "success"
    ALREADY_CLAIMED = "already_claimed"
    INSUFFICIENT_BALANCE = "insufficient_balance"


@dataclass
class ClaimAttemptResult:
    status: ClaimStatus
    balance: Optional[int] = None


def connect():
    """Connect to the SQLite database."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _get_alembic_config() -> Config:
    """Build an Alembic configuration pointing at the project's migration setup."""
    config = Config(ALEMBIC_INI_PATH)
    config.set_main_option("script_location", ALEMBIC_SCRIPT_LOCATION)
    config.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH}")
    return config


def _has_table(table_name: str) -> bool:
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


def run_migrations():
    """Apply Alembic migrations to bring the database schema up to date."""
    config = _get_alembic_config()
    if not _has_table("alembic_version") and (_has_table("cards") or _has_table("user_rolls")):
        logger.info(
            "Existing SQLite schema detected without Alembic metadata; stamping baseline revision %s",
            INITIAL_ALEMBIC_REVISION,
        )
        command.stamp(config, INITIAL_ALEMBIC_REVISION)
    try:
        command.upgrade(config, "head")
    except Exception:
        logger.exception("Failed to apply database migrations")
        raise


def create_tables():
    """Backwards-compatible wrapper that now applies Alembic migrations."""
    run_migrations()


def add_card(base_name, modifier, rarity, image_b64, chat_id=None):
    """Add a new card to the database."""
    conn = connect()
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()
    if chat_id is None:
        chat_id = os.getenv("GROUP_CHAT_ID")
    if chat_id is not None:
        chat_id = str(chat_id)
    cursor.execute(
        """
        INSERT INTO cards (base_name, modifier, rarity, image_b64, chat_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (base_name, modifier, rarity, image_b64, chat_id, now),
    )
    card_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return card_id


def claim_card(card_id, owner, user_id=None, chat_id=None):
    """Attempt to claim a card for a user.

    Returns a ClaimAttemptResult indicating whether the claim succeeded, failed because the
    card was already owned, or failed due to insufficient balance. When tracking is possible
    (user_id and chat_id provided), the result includes the remaining balance after the attempt.
    """

    conn = connect()
    cursor = conn.cursor()
    chat_id_value = str(chat_id) if chat_id is not None else None

    try:
        # Fetch current balance when tracking is possible
        balance: Optional[int] = None
        if user_id is not None and chat_id_value is not None:
            balance = _get_claim_balance(cursor, user_id, chat_id_value)
            if balance < 1:
                conn.rollback()
                return ClaimAttemptResult(ClaimStatus.INSUFFICIENT_BALANCE, balance)

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
            return ClaimAttemptResult(ClaimStatus.ALREADY_CLAIMED, balance)

        # Claim the card
        if user_id is not None:
            cursor.execute(
                "UPDATE cards SET owner = ?, user_id = ? WHERE id = ? AND owner IS NULL",
                (owner, user_id, card_id),
            )
        else:
            cursor.execute(
                "UPDATE cards SET owner = ? WHERE id = ? AND owner IS NULL", (owner, card_id)
            )

        updated = cursor.rowcount > 0

        if not updated:
            conn.rollback()
            return ClaimAttemptResult(ClaimStatus.ALREADY_CLAIMED, balance)

        remaining_balance = balance
        if user_id is not None and chat_id_value is not None:
            remaining_balance = _update_claim_balance(cursor, user_id, chat_id_value, -1)

        conn.commit()
        return ClaimAttemptResult(ClaimStatus.SUCCESS, remaining_balance)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_claim_row(cursor: sqlite3.Cursor, user_id: int, chat_id: str) -> None:
    cursor.execute(
        """
        INSERT INTO claims (user_id, chat_id, balance)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, chat_id) DO NOTHING
        """,
        (user_id, chat_id),
    )


def _get_claim_balance(cursor: sqlite3.Cursor, user_id: int, chat_id: str) -> int:
    _ensure_claim_row(cursor, user_id, chat_id)
    cursor.execute(
        "SELECT balance FROM claims WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id),
    )
    row = cursor.fetchone()
    if row and row[0] is not None:
        return int(row[0])
    return 1


def _update_claim_balance(cursor: sqlite3.Cursor, user_id: int, chat_id: str, delta: int) -> int:
    _ensure_claim_row(cursor, user_id, chat_id)
    if delta != 0:
        cursor.execute(
            "UPDATE claims SET balance = balance + ? WHERE user_id = ? AND chat_id = ?",
            (delta, user_id, chat_id),
        )
        cursor.execute(
            "UPDATE claims SET balance = CASE WHEN balance < 0 THEN 0 ELSE balance END WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
    return _get_claim_balance(cursor, user_id, chat_id)


def get_claim_balance(user_id: int, chat_id: str) -> int:
    conn = connect()
    cursor = conn.cursor()
    try:
        return _get_claim_balance(cursor, user_id, str(chat_id))
    finally:
        conn.close()


def increment_claim_balance(user_id: int, chat_id: str, amount: int = 1) -> int:
    if amount <= 0:
        return get_claim_balance(user_id, chat_id)
    conn = connect()
    cursor = conn.cursor()
    try:
        new_balance = _update_claim_balance(cursor, user_id, str(chat_id), amount)
        conn.commit()
        return new_balance
    finally:
        conn.close()


def get_username_for_user_id(user_id: int) -> Optional[str]:
    """Return the username associated with a user_id, falling back to card ownership."""
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT username FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        if row and row[0]:
            return row[0]

        cursor.execute(
            "SELECT owner FROM cards WHERE user_id = ? AND owner IS NOT NULL ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        )
        fallback = cursor.fetchone()
        if fallback and fallback[0]:
            return fallback[0]
        return None
    finally:
        conn.close()


def get_user_id_by_username(username: str) -> Optional[int]:
    """Resolve a username to a user_id if available."""
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id FROM users WHERE username = ? COLLATE NOCASE",
            (username,),
        )
        row = cursor.fetchone()
        if row and row[0] is not None:
            return int(row[0])

        cursor.execute(
            "SELECT user_id FROM cards WHERE owner = ? COLLATE NOCASE AND user_id IS NOT NULL ORDER BY created_at DESC LIMIT 1",
            (username,),
        )
        fallback = cursor.fetchone()
        if fallback and fallback[0] is not None:
            return int(fallback[0])
        return None
    finally:
        conn.close()


def get_user_collection(user_id: int, chat_id: Optional[str] = None):
    """Get all cards owned by a user (by user_id), optionally scoped to a chat."""
    conn = connect()
    try:
        cursor = conn.cursor()

        username = get_username_for_user_id(user_id)

        conditions = ["user_id = ?"]
        parameters: list[Any] = [user_id]

        if username:
            conditions.append("owner = ? COLLATE NOCASE")
            parameters.append(username)

        query = (
            "SELECT id, base_name, modifier, rarity, owner, user_id, attempted_by, file_id, chat_id, created_at "
            "FROM cards WHERE (" + " OR ".join(conditions) + ")"
        )

        if chat_id is not None:
            query += " AND chat_id = ?"
            parameters.append(str(chat_id))

        query += (
            " ORDER BY CASE rarity WHEN 'Legendary' THEN 1 WHEN 'Epic' THEN 2 WHEN 'Rare' THEN 3 ELSE 4 END, "
            "base_name, modifier"
        )

        cursor.execute(query, tuple(parameters))
        cards = [Card(**row) for row in cursor.fetchall()]
        return cards
    finally:
        conn.close()


def get_user_cards_by_rarity(
    user_id: int,
    username: Optional[str],
    rarity: str,
    chat_id: Optional[str] = None,
    limit: Optional[int] = None,
):
    """Return cards owned by the user for a specific rarity, optionally limited in count."""

    conn = connect()
    try:
        cursor = conn.cursor()

        owner_clauses = []
        parameters: list[Any] = []

        if user_id is not None:
            owner_clauses.append("user_id = ?")
            parameters.append(user_id)

        if username:
            owner_clauses.append("owner = ? COLLATE NOCASE")
            parameters.append(username)

        if not owner_clauses:
            return []

        query = (
            "SELECT id, base_name, modifier, rarity, owner, user_id, attempted_by, file_id, chat_id, created_at, image_b64 "
            "FROM cards WHERE (" + " OR ".join(owner_clauses) + ") AND rarity = ?"
        )
        parameters.append(rarity)

        if chat_id is not None:
            query += " AND chat_id = ?"
            parameters.append(str(chat_id))

        query += " ORDER BY COALESCE(created_at, ''), id"

        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)

        cursor.execute(query, tuple(parameters))
        rows = cursor.fetchall()
        return [CardWithImage(**row) for row in rows]
    finally:
        conn.close()


def get_all_cards(chat_id: Optional[str] = None):
    """Get all cards that have an owner, optionally filtered by chat."""
    conn = connect()
    try:
        cursor = conn.cursor()
        query = (
            "SELECT id, base_name, modifier, rarity, owner, user_id, attempted_by, file_id, chat_id, created_at "
            "FROM cards WHERE owner IS NOT NULL"
        )
        parameters: list[Any] = []

        if chat_id is not None:
            query += " AND chat_id = ?"
            parameters.append(str(chat_id))

        query += (
            " ORDER BY CASE rarity WHEN 'Legendary' THEN 1 WHEN 'Epic' THEN 2 WHEN 'Rare' THEN 3 ELSE 4 END, "
            "base_name, modifier"
        )

        cursor.execute(query, tuple(parameters))
        cards = [Card(**row) for row in cursor.fetchall()]
        return cards
    finally:
        conn.close()


def get_card(card_id):
    """Get a card by its ID."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
    card_data = cursor.fetchone()
    conn.close()
    return CardWithImage(**card_data) if card_data else None


def get_card_image(card_id: int) -> str | None:
    """Get the base64 encoded image for a card."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT image_b64 FROM cards WHERE id = ?", (card_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


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


def get_all_users_with_cards(chat_id: Optional[str] = None):
    """Get all unique users who have claimed cards, optionally scoped to a chat."""
    conn = connect()
    cursor = conn.cursor()
    query = "SELECT DISTINCT owner FROM cards WHERE owner IS NOT NULL"
    parameters: list[Any] = []

    if chat_id is not None:
        query += " AND chat_id = ?"
        parameters.append(str(chat_id))

    query += " ORDER BY owner"

    cursor.execute(query, tuple(parameters))
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users


def get_last_roll_time(user_id: int, chat_id: str):
    """Get the last roll timestamp for a user within a specific chat."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT last_roll_timestamp FROM user_rolls WHERE user_id = ? AND chat_id = ?",
        (user_id, str(chat_id)),
    )
    result = cursor.fetchone()
    conn.close()
    if result:
        return datetime.datetime.fromisoformat(result[0])
    return None


def can_roll(user_id: int, chat_id: str):
    """Check if a user can roll (24 hours since last roll) within a chat."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT last_roll_timestamp FROM user_rolls WHERE user_id = ? AND chat_id = ?",
        (user_id, str(chat_id)),
    )
    result = cursor.fetchone()
    conn.close()
    if result:
        last_roll_time = datetime.datetime.fromisoformat(result[0])
        time_since_last_roll = datetime.datetime.now() - last_roll_time
        if time_since_last_roll.total_seconds() < 24 * 60 * 60:  # 24 hours in seconds
            return False
    return True


def record_roll(user_id: int, chat_id: str):
    """Record a user's roll timestamp for a specific chat."""
    conn = connect()
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cursor.execute(
        """
        INSERT OR REPLACE INTO user_rolls (user_id, chat_id, last_roll_timestamp)
        VALUES (?, ?, ?)
        """,
        (user_id, str(chat_id), now),
    )
    conn.commit()
    conn.close()


def swap_card_owners(card_id1, card_id2):
    """Swap the owners of two cards."""
    conn = connect()
    cursor = conn.cursor()
    try:
        # Get current owners
        cursor.execute("SELECT owner, user_id FROM cards WHERE id = ?", (card_id1,))
        owner1_row = cursor.fetchone()
        owner1 = owner1_row[0]
        user_id1 = owner1_row[1]

        cursor.execute("SELECT owner, user_id FROM cards WHERE id = ?", (card_id2,))
        owner2_row = cursor.fetchone()
        owner2 = owner2_row[0]
        user_id2 = owner2_row[1]

        # Swap owners
        cursor.execute(
            "UPDATE cards SET owner = ?, user_id = ? WHERE id = ?",
            (owner2, user_id2, card_id1),
        )
        cursor.execute(
            "UPDATE cards SET owner = ?, user_id = ? WHERE id = ?",
            (owner1, user_id1, card_id2),
        )

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


def delete_card(card_id):
    """Delete a card from the database."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    logger.info(f"Deleted card {card_id}: {deleted}")
    return deleted


def is_reroll_expired(card_id):
    """Check if the reroll time limit (5 minutes) has expired for a card."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT created_at FROM cards WHERE id = ?", (card_id,))
    result = cursor.fetchone()
    conn.close()

    if not result or not result[0]:
        return True  # No creation time found, consider expired

    created_at = datetime.datetime.fromisoformat(result[0])
    time_since_creation = datetime.datetime.now() - created_at
    return time_since_creation.total_seconds() > 5 * 60  # 5 minutes in seconds


def upsert_user(
    user_id: int,
    username: str,
    display_name: Optional[str] = None,
    profile_imageb64: Optional[str] = None,
) -> None:
    """Insert or update a user record."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (user_id, username, display_name, profile_imageb64)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            display_name = COALESCE(excluded.display_name, users.display_name),
            profile_imageb64 = COALESCE(excluded.profile_imageb64, users.profile_imageb64)
        """,
        (user_id, username, display_name, profile_imageb64),
    )
    conn.commit()
    conn.close()


def update_user_profile(user_id: int, display_name: str, profile_imageb64: str) -> bool:
    """Update the display name and profile image for a user."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET display_name = ?, profile_imageb64 = ? WHERE user_id = ?",
        (display_name, profile_imageb64, user_id),
    )
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def get_user(user_id: int) -> Optional[User]:
    """Fetch a user record by ID."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return User(**row) if row else None


def user_exists(user_id: int) -> bool:
    """Check whether a user exists in the users table."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def get_random_chat_user_with_profile(chat_id: str) -> Optional[User]:
    """Return a random user enrolled in the chat with a stored profile image."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT u.user_id, u.username, u.display_name, u.profile_imageb64
        FROM chats c
        INNER JOIN users u ON c.user_id = u.user_id
        WHERE c.chat_id = ?
          AND u.profile_imageb64 IS NOT NULL
          AND TRIM(u.profile_imageb64) != ''
                    AND u.display_name IS NOT NULL
                    AND TRIM(u.display_name) != ''
        ORDER BY RANDOM()
        LIMIT 1
        """,
        (str(chat_id),),
    )
    row = cursor.fetchone()
    conn.close()
    return User(**row) if row else None


def add_user_to_chat(chat_id: str, user_id: int) -> bool:
    """Add a user to a chat; returns True if inserted."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO chats (chat_id, user_id) VALUES (?, ?)",
        (str(chat_id), user_id),
    )
    inserted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return inserted


def is_user_in_chat(chat_id: str, user_id: int) -> bool:
    """Check whether a user is enrolled in a chat."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM chats WHERE chat_id = ? AND user_id = ?",
        (str(chat_id), user_id),
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


create_tables()
