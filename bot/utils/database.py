import atexit
import base64
import datetime
import html
import logging
import os
import sqlite3
import json
import threading
from contextlib import suppress, contextmanager
from typing import Optional, Any, List, Dict
from zoneinfo import ZoneInfo

from alembic import command
from alembic.config import Config
from pydantic import BaseModel

from settings.constants import DB_PATH
from utils.image import ImageUtil

logger = logging.getLogger(__name__)

# Import GeminiUtil for slot icon generation
try:
    from utils.gemini import GeminiUtil

    GEMINI_AVAILABLE = True
except ImportError:
    logger.warning("GeminiUtil not available. Slot icon generation will be skipped.")
    GEMINI_AVAILABLE = False

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
ALEMBIC_INI_PATH = os.path.join(PROJECT_ROOT, "alembic.ini")
ALEMBIC_SCRIPT_LOCATION = os.path.join(PROJECT_ROOT, "alembic")
INITIAL_ALEMBIC_REVISION = "20240924_0001"


class DatabaseConfig:
    """Configuration for database connection pool."""

    def __init__(self, pool_size: int = 6, timeout_seconds: int = 30, busy_timeout_ms: int = 5000):
        """
        Initialize database configuration.

        Args:
            pool_size: Size of the connection pool
            timeout_seconds: Connection timeout in seconds
            busy_timeout_ms: SQLite busy timeout in milliseconds
        """
        if pool_size <= 0:
            logger.warning("pool_size must be positive; falling back to 6")
            pool_size = 6
        if timeout_seconds <= 0:
            logger.warning("timeout_seconds must be positive; falling back to 30")
            timeout_seconds = 30
        if busy_timeout_ms <= 0:
            logger.warning("busy_timeout_ms must be positive; falling back to 5000")
            busy_timeout_ms = 5000

        self.pool_size = pool_size
        self.timeout_seconds = timeout_seconds
        self.busy_timeout_ms = busy_timeout_ms


# Global configuration - will be set by initialize_database()
_db_config: Optional[DatabaseConfig] = None


def initialize_database(
    pool_size: int = 6, timeout_seconds: int = 30, busy_timeout_ms: int = 5000
) -> None:
    """
    Initialize database configuration.

    This should be called once at application startup before any database operations.

    Args:
        pool_size: Size of the connection pool (default: 6)
        timeout_seconds: Connection timeout in seconds (default: 30)
        busy_timeout_ms: SQLite busy timeout in milliseconds (default: 5000)
    """
    global _db_config
    _db_config = DatabaseConfig(pool_size, timeout_seconds, busy_timeout_ms)
    logger.info(
        "Database initialized with pool_size=%d, timeout_seconds=%d, busy_timeout_ms=%d",
        _db_config.pool_size,
        _db_config.timeout_seconds,
        _db_config.busy_timeout_ms,
    )


def _get_config() -> DatabaseConfig:
    """Get the database configuration, initializing with defaults if needed."""
    global _db_config
    if _db_config is None:
        _db_config = DatabaseConfig()
        logger.warning("Database not explicitly initialized; using default configuration")
    return _db_config


class _ReusableConnection(sqlite3.Connection):
    def close(self):  # type: ignore[override]
        _release_connection(self)


_POOL_LOCK = threading.Lock()
_WAL_LOCK = threading.Lock()
_CONNECTION_POOL: list[_ReusableConnection] = []
_WAL_ENABLED = False


def _configure_connection(conn: _ReusableConnection) -> None:
    config = _get_config()
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={config.busy_timeout_ms}")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")

    global _WAL_ENABLED
    if not _WAL_ENABLED:
        with _WAL_LOCK:
            if not _WAL_ENABLED:
                try:
                    result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
                    if result and str(result[0]).lower() == "wal":
                        _WAL_ENABLED = True
                        logger.info("SQLite database journal mode switched to WAL")
                    else:
                        logger.warning("Unable to enable WAL journal mode; result=%s", result)
                except sqlite3.DatabaseError as exc:
                    logger.warning("Failed to enable WAL journal mode: %s", exc)


def _create_connection() -> _ReusableConnection:
    config = _get_config()
    conn = sqlite3.connect(
        DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        check_same_thread=False,
        timeout=config.timeout_seconds,
        factory=_ReusableConnection,
    )
    setattr(conn, "_released", False)
    _configure_connection(conn)
    return conn


def _is_connection_alive(conn: _ReusableConnection) -> bool:
    try:
        conn.execute("SELECT 1")
        return True
    except sqlite3.Error:
        return False


def _acquire_connection() -> _ReusableConnection:
    with _POOL_LOCK:
        while _CONNECTION_POOL:
            conn = _CONNECTION_POOL.pop()
            if _is_connection_alive(conn):
                setattr(conn, "_released", False)
                try:
                    config = _get_config()
                    conn.row_factory = sqlite3.Row
                    conn.execute(f"PRAGMA busy_timeout={config.busy_timeout_ms}")
                    conn.execute("PRAGMA foreign_keys=ON")
                    conn.execute("PRAGMA synchronous=NORMAL")
                    return conn
                except sqlite3.Error:
                    with suppress(sqlite3.Error):
                        super(_ReusableConnection, conn).close()
                    continue
            with suppress(sqlite3.Error):
                super(_ReusableConnection, conn).close()

    conn = _create_connection()
    return conn


def _release_connection(conn: _ReusableConnection) -> None:
    if getattr(conn, "_released", False):
        return

    setattr(conn, "_released", True)

    with suppress(sqlite3.Error):
        conn.rollback()

    config = _get_config()
    with _POOL_LOCK:
        if len(_CONNECTION_POOL) < config.pool_size:
            _CONNECTION_POOL.append(conn)
        else:
            with suppress(sqlite3.Error):
                super(_ReusableConnection, conn).close()


def _cleanup_connection_pool() -> None:
    with _POOL_LOCK:
        while _CONNECTION_POOL:
            conn = _CONNECTION_POOL.pop()
            with suppress(sqlite3.Error):
                super(_ReusableConnection, conn).close()


atexit.register(_cleanup_connection_pool)


def _load_config() -> Dict[str, Any]:
    """Load configuration from config.json."""
    config_path = os.path.join(PROJECT_ROOT, "config.json")
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to load config: {e}. Using defaults.")
        return {"SPINS_PER_DAY": 10}


def _get_spins_config() -> tuple[int, int]:
    """Get SPINS_PER_REFRESH and SPINS_REFRESH_HOURS from config. Returns (spins_per_refresh, hours_per_refresh)."""
    config = _load_config()
    return config.get("SPINS_PER_REFRESH", 5), config.get("SPINS_REFRESH_HOURS", 3)


def _generate_slot_icon(image_b64: str) -> Optional[str]:
    """Generate slot machine icon from base64 image. Returns base64 slot icon or None if failed."""
    if not GEMINI_AVAILABLE:
        return None

    try:
        # Get API credentials from environment
        google_api_key = os.getenv("GOOGLE_API_KEY")
        image_gen_model = os.getenv("IMAGE_GEN_MODEL")

        if not google_api_key or not image_gen_model:
            logger.warning(
                "GOOGLE_API_KEY or IMAGE_GEN_MODEL not set, skipping slot icon generation"
            )
            return None

        gemini_util = GeminiUtil(google_api_key, image_gen_model)
        slot_icon_b64 = gemini_util.generate_slot_machine_icon(base_image_b64=image_b64)
        if slot_icon_b64:
            logger.info("Slot machine icon generated successfully")
        else:
            logger.warning("Failed to generate slot machine icon")
        return slot_icon_b64
    except Exception as e:
        logger.error(f"Error generating slot machine icon: {e}")
        return None


class User(BaseModel):
    user_id: int
    username: str
    display_name: Optional[str]
    profile_imageb64: Optional[str]
    slot_iconb64: Optional[str] = None


class Card(BaseModel):
    id: int
    base_name: str
    modifier: str
    rarity: str
    owner: Optional[str]
    user_id: Optional[int]
    file_id: Optional[str]
    chat_id: Optional[str]
    created_at: Optional[str]
    locked: bool = False
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    set_id: Optional[int] = None

    def title(self, include_id: bool = False, include_rarity: bool = False):
        """Return the card's title, optionally including rarity and ID.

        Args:
            include_rarity: If True, includes rarity prefix. Default is False.
            include_id: If True, includes card ID in brackets as prefix. Default is False.

        Returns:
            HTML-escaped title text.
        """
        parts = []

        if include_id:
            parts.append(f"[{self.id}]")

        if include_rarity:
            parts.append(self.rarity)

        parts.append(self.modifier)
        parts.append(self.base_name)

        title_text = " ".join(parts).strip()
        return html.escape(title_text)


class CardWithImage(Card):
    image_b64: str

    def get_media(self):
        """Return file_id if available, otherwise return decoded base64 image data."""
        if self.file_id:
            return self.file_id
        return base64.b64decode(self.image_b64)


class Claim(BaseModel):
    user_id: int
    chat_id: str
    balance: int


class RolledCard(BaseModel):
    roll_id: int
    original_card_id: int
    rerolled_card_id: Optional[int] = None
    created_at: str
    original_roller_id: int
    rerolled: bool
    being_rerolled: bool
    attempted_by: Optional[str]
    is_locked: bool

    @property
    def current_card_id(self) -> int:
        if self.rerolled and self.rerolled_card_id:
            return self.rerolled_card_id
        return self.original_card_id

    @property
    def card_id(self) -> int:
        """Backward-compatible alias for the active card id."""
        return self.current_card_id


class Character(BaseModel):
    id: int
    chat_id: str
    name: str
    imageb64: str
    slot_iconb64: Optional[str] = None


class Spins(BaseModel):
    user_id: int
    chat_id: str
    count: int
    refresh_timestamp: str


class MinesweeperGame(BaseModel):
    """Represents a minesweeper game state."""

    id: int
    user_id: int
    chat_id: str
    bet_card_id: int
    bet_card_title: Optional[str] = None  # Store card title in case card is deleted
    bet_card_rarity: Optional[str] = None  # Store card rarity in case card is deleted
    mine_positions: List[int]
    claim_point_positions: List[int]
    revealed_cells: List[int]
    status: str
    moves_count: int
    reward_card_id: Optional[int]
    started_timestamp: datetime.datetime
    last_updated_timestamp: datetime.datetime
    source_type: Optional[str] = None  # "user" or "character"
    source_id: Optional[int] = None  # user_id for users, character id for characters

    def to_dict(self) -> Dict[str, Any]:
        """Convert game state to dictionary for API responses."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "bet_card_id": self.bet_card_id,
            "mine_positions": self.mine_positions,
            "claim_point_positions": self.claim_point_positions,
            "revealed_cells": self.revealed_cells,
            "status": self.status,
            "moves_count": self.moves_count,
            "reward_card_id": self.reward_card_id,
            "started_timestamp": self.started_timestamp.isoformat(),
            "last_updated_timestamp": self.last_updated_timestamp.isoformat(),
            "source_type": self.source_type,
            "source_id": self.source_id,
        }


def connect():
    """Connect to the SQLite database."""
    dir_path = os.path.dirname(DB_PATH)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    conn = _acquire_connection()
    return conn


@contextmanager
def _managed_connection(commit: bool = False):
    """Yield a connection/cursor pair with consistent commit/rollback semantics."""

    conn = connect()
    try:
        cursor = conn.cursor()
        yield conn, cursor
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _get_alembic_config() -> Config:
    """Build an Alembic configuration pointing at the project's migration setup."""
    config = Config(ALEMBIC_INI_PATH)
    config.set_main_option("script_location", ALEMBIC_SCRIPT_LOCATION)
    config.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH}")
    return config


def _has_table(table_name: str) -> bool:
    with _managed_connection() as (_, cursor):
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        )
        return cursor.fetchone() is not None


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


def add_card(
    base_name: str,
    modifier: str,
    rarity: str,
    image_b64: str,
    chat_id: Optional[str],
    source_type: str,
    source_id: int,
    set_id: Optional[int] = None,
) -> int:
    """Add a new card to the database.

    Returns:
        int: The card ID of the newly created card
    """
    now = datetime.datetime.now().isoformat()
    if chat_id is not None:
        chat_id = str(chat_id)

    image_thumb_b64: Optional[str] = None
    if image_b64:
        try:
            image_bytes = base64.b64decode(image_b64)
            thumb_bytes = ImageUtil.compress_to_fraction(image_bytes, scale_factor=1 / 4)
            image_thumb_b64 = base64.b64encode(thumb_bytes).decode("utf-8")
        except Exception as exc:
            logger.warning("Failed to generate thumbnail for new card: %s", exc)

    with _managed_connection(commit=True) as (_, cursor):
        # Insert card metadata (without images)
        cursor.execute(
            """
            INSERT INTO cards (base_name, modifier, rarity, chat_id, created_at, source_type, source_id, set_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                base_name,
                modifier,
                rarity,
                chat_id,
                now,
                source_type,
                source_id,
                set_id,
            ),
        )
        card_id = cursor.lastrowid

        # Insert image data into separate table if available
        if image_b64 or image_thumb_b64:
            cursor.execute(
                """
                INSERT INTO card_images (card_id, image_b64, image_thumb_b64)
                VALUES (?, ?, ?)
            """,
                (card_id, image_b64, image_thumb_b64),
            )

        return card_id


def add_card_from_generated(generated_card, chat_id: Optional[str]) -> int:
    """
    Add a card to the database from a GeneratedCard object.

    This is a convenience wrapper around add_card that accepts a GeneratedCard
    (from utils.rolling) and extracts all the necessary fields.

    Args:
        generated_card: A GeneratedCard instance from utils.rolling
        chat_id: The chat ID to associate with this card

    Returns:
        int: The database ID of the newly created card
    """
    return add_card(
        base_name=generated_card.base_name,
        modifier=generated_card.modifier,
        rarity=generated_card.rarity,
        image_b64=generated_card.image_b64,
        chat_id=chat_id,
        source_type=generated_card.source_type,
        source_id=generated_card.source_id,
        set_id=generated_card.set_id,
    )


def upsert_set(set_id: int, name: str) -> None:
    """Insert or update a set in the database."""

    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            """
            INSERT INTO sets (id, name)
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name
        """,
            (set_id, name),
        )


def get_set_id_by_name(name: str) -> Optional[int]:
    """Get the set ID for a given set name."""

    with _managed_connection() as (_, cursor):
        cursor.execute(
            "SELECT id FROM sets WHERE name = ?",
            (name,),
        )
        row = cursor.fetchone()
        return row["id"] if row else None


def try_claim_card(card_id: int, owner: str, user_id: Optional[int] = None) -> bool:
    """Attempt to claim a card for a user without touching claim balances."""

    with _managed_connection(commit=True) as (_, cursor):
        if user_id is not None:
            cursor.execute(
                "UPDATE cards SET owner = ?, user_id = ? WHERE id = ? AND owner IS NULL",
                (owner, user_id, card_id),
            )
        else:
            cursor.execute(
                "UPDATE cards SET owner = ? WHERE id = ? AND owner IS NULL",
                (owner, card_id),
            )

        return cursor.rowcount > 0


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
    with _managed_connection() as (_, cursor):
        return _get_claim_balance(cursor, user_id, str(chat_id))


def increment_claim_balance(user_id: int, chat_id: str, amount: int = 1) -> int:
    if amount <= 0:
        return get_claim_balance(user_id, chat_id)
    with _managed_connection(commit=True) as (_, cursor):
        return _update_claim_balance(cursor, user_id, str(chat_id), amount)


def reduce_claim_points(user_id: int, chat_id: str, amount: int = 1) -> Optional[int]:
    """
    Attempt to reduce claim points for a user.

    Returns the remaining balance if successful, or None if insufficient balance.
    """
    if amount <= 0:
        return get_claim_balance(user_id, chat_id)

    with _managed_connection(commit=True) as (_, cursor):
        current_balance = _get_claim_balance(cursor, user_id, str(chat_id))
        if current_balance < amount:
            return None  # Insufficient balance

        return _update_claim_balance(cursor, user_id, str(chat_id), -amount)


def get_username_for_user_id(user_id: int) -> Optional[str]:
    """Return the username associated with a user_id, falling back to card ownership."""
    with _managed_connection() as (_, cursor):
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


def get_user_id_by_username(username: str) -> Optional[int]:
    """Resolve a username to a user_id if available."""
    with _managed_connection() as (_, cursor):
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


def get_most_frequent_chat_id_for_user(user_id: int) -> Optional[str]:
    """
    Get the most frequently used chat_id among a user's cards.

    Args:
        user_id: The user's ID

    Returns:
        The most frequently used chat_id, or None if user has no cards
    """
    with _managed_connection() as (_, cursor):
        cursor.execute(
            """
            SELECT chat_id, COUNT(*) as count 
            FROM cards 
            WHERE user_id = ? AND chat_id IS NOT NULL
            GROUP BY chat_id 
            ORDER BY count DESC 
            LIMIT 1
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        if row and row[0]:
            return str(row[0])
        return None


def get_user_collection(user_id: int, chat_id: Optional[str] = None) -> List[Card]:
    """Get all cards owned by a user (by user_id), optionally scoped to a chat.

    Returns:
        List[Card]: List of Card objects owned by the user
    """
    username = get_username_for_user_id(user_id)

    conditions = ["user_id = ?"]
    parameters: list[Any] = [user_id]

    if username:
        conditions.append("owner = ? COLLATE NOCASE")
        parameters.append(username)

    query = (
        "SELECT id, base_name, modifier, rarity, owner, user_id, file_id, chat_id, created_at, locked "
        "FROM cards WHERE (" + " OR ".join(conditions) + ")"
    )

    if chat_id is not None:
        query += " AND chat_id = ?"
        parameters.append(str(chat_id))

    query += (
        " ORDER BY CASE rarity WHEN 'Unique' THEN 1 WHEN 'Legendary' THEN 2 WHEN 'Epic' THEN 3 WHEN 'Rare' THEN 4 ELSE 5 END, "
        "base_name, modifier"
    )

    with _managed_connection() as (_, cursor):
        cursor.execute(query, tuple(parameters))
        return [Card(**row) for row in cursor.fetchall()]


def get_user_cards_by_rarity(
    user_id: int,
    username: Optional[str],
    rarity: str,
    chat_id: Optional[str] = None,
    limit: Optional[int] = None,
    unlocked: bool = False,
) -> List[Card]:
    """Return cards owned by the user for a specific rarity, optionally limited in count."""

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
        "SELECT id, base_name, modifier, rarity, owner, user_id, file_id, chat_id, created_at, locked "
        "FROM cards "
        "WHERE (" + " OR ".join(owner_clauses) + ") AND rarity = ?"
    )
    parameters.append(rarity)

    if chat_id is not None:
        query += " AND chat_id = ?"
        parameters.append(str(chat_id))

    if unlocked:
        query += " AND locked = 0"

    query += " ORDER BY COALESCE(created_at, ''), id"

    if limit is not None:
        query += " LIMIT ?"
        parameters.append(limit)

    with _managed_connection() as (_, cursor):
        cursor.execute(query, tuple(parameters))
        return [Card(**row) for row in cursor.fetchall()]


def get_all_cards(chat_id: Optional[str] = None) -> List[Card]:
    """Get all cards that have an owner, optionally filtered by chat."""
    query = (
        "SELECT id, base_name, modifier, rarity, owner, user_id, file_id, chat_id, created_at, locked "
        "FROM cards WHERE owner IS NOT NULL"
    )
    parameters: list[Any] = []

    if chat_id is not None:
        query += " AND chat_id = ?"
        parameters.append(str(chat_id))

    query += (
        " ORDER BY CASE rarity WHEN 'Unique' THEN 1 WHEN 'Legendary' THEN 2 WHEN 'Epic' THEN 3 WHEN 'Rare' THEN 4 ELSE 5 END, "
        "base_name, modifier"
    )

    with _managed_connection() as (_, cursor):
        cursor.execute(query, tuple(parameters))
        return [Card(**row) for row in cursor.fetchall()]


def get_card(card_id) -> Optional[CardWithImage]:
    """Get a card by its ID."""
    with _managed_connection() as (_, cursor):
        cursor.execute(
            """
            SELECT c.*, ci.image_b64
            FROM cards c
            LEFT JOIN card_images ci ON c.id = ci.card_id
            WHERE c.id = ?
            """,
            (card_id,),
        )
        card_data = cursor.fetchone()
        return CardWithImage(**card_data) if card_data else None


def get_card_image(card_id: int) -> str | None:
    """Get the base64 encoded image for a card."""
    with _managed_connection() as (_, cursor):
        cursor.execute("SELECT image_b64 FROM card_images WHERE card_id = ?", (card_id,))
        result = cursor.fetchone()
        return result[0] if result else None


def get_card_images_batch(card_ids: List[int]) -> dict[int, str]:
    """Get thumbnail base64 images for multiple cards, generating them when missing."""
    if not card_ids:
        return {}

    with _managed_connection(commit=True) as (_, cursor):
        placeholders = ",".join(["?"] * len(card_ids))
        cursor.execute(
            f"SELECT card_id, image_thumb_b64, image_b64 FROM card_images WHERE card_id IN ({placeholders})",
            tuple(card_ids),
        )
        rows = cursor.fetchall()
        fetched: dict[int, str] = {}
        for row in rows:
            card_id = int(row["card_id"])
            thumb = row["image_thumb_b64"]
            full = row["image_b64"]

            if thumb:
                fetched[card_id] = thumb
                continue

            if not full:
                continue

            try:
                image_bytes = base64.b64decode(full)
                thumb_bytes = ImageUtil.compress_to_fraction(image_bytes, scale_factor=1 / 4)
                thumb_b64 = base64.b64encode(thumb_bytes).decode("utf-8")
                cursor.execute(
                    "UPDATE card_images SET image_thumb_b64 = ? WHERE card_id = ?",
                    (thumb_b64, card_id),
                )
                fetched[card_id] = thumb_b64
            except Exception as exc:
                logger.warning(
                    "Failed to generate thumbnail during batch fetch for card %s: %s",
                    card_id,
                    exc,
                )

        ordered: dict[int, str] = {}
        for card_id in card_ids:
            image = fetched.get(card_id)
            if image is not None:
                ordered[card_id] = image
        return ordered


def get_total_cards_count() -> int:
    """Get the total number of cards ever generated."""
    with _managed_connection() as (_, cursor):
        cursor.execute("SELECT COUNT(*) FROM cards WHERE owner IS NOT NULL")
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 0


def get_user_stats(username):
    """Get card statistics for a user."""
    with _managed_connection() as (_, cursor):
        cursor.execute("SELECT COUNT(*) FROM cards WHERE owner = ?", (username,))
        owned_row = cursor.fetchone()
        owned_count = int(owned_row[0]) if owned_row and owned_row[0] is not None else 0

        rarities = ["Unique", "Legendary", "Epic", "Rare", "Common"]
        rarity_counts = {}
        for rarity in rarities:
            cursor.execute(
                "SELECT COUNT(*) FROM cards WHERE owner = ? AND rarity = ?",
                (username, rarity),
            )
            rarity_row = cursor.fetchone()
            rarity_counts[rarity] = (
                int(rarity_row[0]) if rarity_row and rarity_row[0] is not None else 0
            )

    total_count = get_total_cards_count()

    return {"owned": owned_count, "total": total_count, "rarities": rarity_counts}


def get_all_users_with_cards(chat_id: Optional[str] = None):
    """Get all unique users who have claimed cards, optionally scoped to a chat."""
    query = "SELECT DISTINCT owner FROM cards WHERE owner IS NOT NULL"
    parameters: list[Any] = []

    if chat_id is not None:
        query += " AND chat_id = ?"
        parameters.append(str(chat_id))

    query += " ORDER BY owner"

    with _managed_connection() as (_, cursor):
        cursor.execute(query, tuple(parameters))
        return [row[0] for row in cursor.fetchall()]


def get_last_roll_time(user_id: int, chat_id: str):
    """Get the last roll timestamp for a user within a specific chat."""
    with _managed_connection() as (_, cursor):
        cursor.execute(
            "SELECT last_roll_timestamp FROM user_rolls WHERE user_id = ? AND chat_id = ?",
            (user_id, str(chat_id)),
        )
        result = cursor.fetchone()
        if result and result[0]:
            return datetime.datetime.fromisoformat(result[0])
        return None


def can_roll(user_id: int, chat_id: str):
    """Check if a user can roll (24 hours since last roll) within a chat."""
    with _managed_connection() as (_, cursor):
        cursor.execute(
            "SELECT last_roll_timestamp FROM user_rolls WHERE user_id = ? AND chat_id = ?",
            (user_id, str(chat_id)),
        )
        result = cursor.fetchone()
        if not result or not result[0]:
            return True

        last_roll_time = datetime.datetime.fromisoformat(result[0])
        time_since_last_roll = datetime.datetime.now() - last_roll_time
        return time_since_last_roll.total_seconds() >= 24 * 60 * 60


def record_roll(user_id: int, chat_id: str):
    """Record a user's roll timestamp for a specific chat."""
    now = datetime.datetime.now().isoformat()
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            """
            INSERT OR REPLACE INTO user_rolls (user_id, chat_id, last_roll_timestamp)
            VALUES (?, ?, ?)
            """,
            (user_id, str(chat_id), now),
        )


def swap_card_owners(card_id1, card_id2) -> bool:
    """Swap the owners of two cards."""
    try:
        with _managed_connection(commit=True) as (_, cursor):
            cursor.execute("SELECT owner, user_id FROM cards WHERE id = ?", (card_id1,))
            owner1_row = cursor.fetchone()
            if not owner1_row:
                return False
            owner1, user_id1 = owner1_row[0], owner1_row[1]

            cursor.execute("SELECT owner, user_id FROM cards WHERE id = ?", (card_id2,))
            owner2_row = cursor.fetchone()
            if not owner2_row:
                return False
            owner2, user_id2 = owner2_row[0], owner2_row[1]

            cursor.execute(
                "UPDATE cards SET owner = ?, user_id = ? WHERE id = ?",
                (owner2, user_id2, card_id1),
            )
            cursor.execute(
                "UPDATE cards SET owner = ?, user_id = ? WHERE id = ?",
                (owner1, user_id1, card_id2),
            )
            return True
    except sqlite3.Error:
        return False


def set_card_owner(card_id: int, owner: str, user_id: Optional[int] = None) -> bool:
    """Set the owner and optional user_id for a card without affecting claim balances."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            "UPDATE cards SET owner = ?, user_id = ? WHERE id = ?",
            (owner, user_id, card_id),
        )
        return cursor.rowcount > 0


def update_card_file_id(card_id, file_id) -> None:
    """Update the Telegram file_id for a card."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute("UPDATE cards SET file_id = ? WHERE id = ?", (file_id, card_id))
    logger.info(f"Updated file_id for card {card_id}: {file_id}")


def update_card_image(card_id: int, image_b64: str) -> None:
    """Update the image for a card, regenerating thumbnail and clearing file_id."""
    # Generate new thumbnail
    image_thumb_b64: Optional[str] = None
    if image_b64:
        try:
            image_bytes = base64.b64decode(image_b64)
            thumb_bytes = ImageUtil.compress_to_fraction(image_bytes, scale_factor=1 / 4)
            image_thumb_b64 = base64.b64encode(thumb_bytes).decode("utf-8")
        except Exception as exc:
            logger.warning("Failed to generate thumbnail for refreshed card %s: %s", card_id, exc)

    # Update card_images with new image and thumbnail, and clear file_id on cards table
    with _managed_connection(commit=True) as (_, cursor):
        # Upsert into card_images table
        cursor.execute(
            """
            INSERT INTO card_images (card_id, image_b64, image_thumb_b64)
            VALUES (?, ?, ?)
            ON CONFLICT(card_id) DO UPDATE SET
                image_b64 = excluded.image_b64,
                image_thumb_b64 = excluded.image_thumb_b64
            """,
            (card_id, image_b64, image_thumb_b64),
        )
        # Clear file_id since we have a new image
        cursor.execute(
            "UPDATE cards SET file_id = NULL WHERE id = ?",
            (card_id,),
        )
    logger.info(f"Updated image for card {card_id}, cleared file_id")


def set_card_locked(card_id: int, is_locked: bool) -> None:
    """Set the locked status for a card."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute("UPDATE cards SET locked = ? WHERE id = ?", (1 if is_locked else 0, card_id))
    logger.info(f"Set locked={is_locked} for card {card_id}")


def clear_all_file_ids():
    """Clear all file_ids from all cards (set to NULL)."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute("UPDATE cards SET file_id = NULL")
        affected_rows = cursor.rowcount
    logger.info(f"Cleared file_ids for {affected_rows} cards")
    return affected_rows


def nullify_card_owner(card_id) -> bool:
    """Set card owner to NULL (for rerolls/burns) instead of deleting."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute("UPDATE cards SET owner = NULL, user_id = NULL WHERE id = ?", (card_id,))
        updated = cursor.rowcount > 0
    logger.info(f"Nullified owner for card {card_id}: {updated}")
    return updated


def delete_card(card_id) -> bool:
    """Delete a card from the database (use sparingly - prefer nullify_card_owner)."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        deleted = cursor.rowcount > 0
    logger.info(f"Deleted card {card_id}: {deleted}")
    return deleted


def upsert_user(
    user_id: int,
    username: str,
    display_name: Optional[str] = None,
    profile_imageb64: Optional[str] = None,
) -> None:
    """Insert or update a user record."""
    with _managed_connection(commit=True) as (_, cursor):
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


def update_user_profile(user_id: int, display_name: str, profile_imageb64: str) -> bool:
    """Update the display name and profile image for a user, and generate slot icon."""
    # Generate slot machine icon
    slot_icon_b64 = _generate_slot_icon(profile_imageb64)

    with _managed_connection(commit=True) as (_, cursor):
        if slot_icon_b64:
            cursor.execute(
                "UPDATE users SET display_name = ?, profile_imageb64 = ?, slot_iconb64 = ? WHERE user_id = ?",
                (display_name, profile_imageb64, slot_icon_b64, user_id),
            )
            logger.info(f"Updated user profile and slot icon for user {user_id}")
        else:
            cursor.execute(
                "UPDATE users SET display_name = ?, profile_imageb64 = ? WHERE user_id = ?",
                (display_name, profile_imageb64, user_id),
            )
            logger.info(f"Updated user profile for user {user_id} (slot icon generation failed)")

        updated = cursor.rowcount > 0
    return updated


def get_user(user_id: int) -> Optional[User]:
    """Fetch a user record by ID."""
    with _managed_connection() as (_, cursor):
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return User(**row) if row else None


def user_exists(user_id: int) -> bool:
    """Check whether a user exists in the users table."""
    with _managed_connection() as (_, cursor):
        cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None


def get_all_chat_users_with_profile(chat_id: str) -> List[User]:
    """Return all users enrolled in the chat with stored profile images and display names."""
    with _managed_connection() as (_, cursor):
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
        """,
            (str(chat_id),),
        )
        rows = cursor.fetchall()
        return [User(**row) for row in rows]


def get_random_chat_user_with_profile(chat_id: str) -> Optional[User]:
    """Return a random user enrolled in the chat with a stored profile image."""
    with _managed_connection() as (_, cursor):
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
        return User(**row) if row else None


def add_user_to_chat(chat_id: str, user_id: int) -> bool:
    """Add a user to a chat; returns True if inserted."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            "INSERT OR IGNORE INTO chats (chat_id, user_id) VALUES (?, ?)",
            (str(chat_id), user_id),
        )
        return cursor.rowcount > 0


def remove_user_from_chat(chat_id: str, user_id: int) -> bool:
    """Remove a user from a chat; returns True if a row was deleted."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            "DELETE FROM chats WHERE chat_id = ? AND user_id = ?",
            (str(chat_id), user_id),
        )
        return cursor.rowcount > 0


def is_user_in_chat(chat_id: str, user_id: int) -> bool:
    """Check whether a user is enrolled in a chat."""
    with _managed_connection() as (_, cursor):
        cursor.execute(
            "SELECT 1 FROM chats WHERE chat_id = ? AND user_id = ?",
            (str(chat_id), user_id),
        )
        return cursor.fetchone() is not None


def get_all_chat_users(chat_id: str) -> List[int]:
    """Get all user IDs enrolled in a specific chat."""
    with _managed_connection() as (_, cursor):
        cursor.execute(
            "SELECT user_id FROM chats WHERE chat_id = ?",
            (str(chat_id),),
        )
        rows = cursor.fetchall()
        return [row[0] for row in rows]


def _row_to_rolled_card(row: sqlite3.Row | None) -> Optional[RolledCard]:
    return RolledCard(**row) if row else None


def _get_roll_row_by_roll_id(cursor: sqlite3.Cursor, roll_id: int) -> Optional[sqlite3.Row]:
    cursor.execute("SELECT * FROM rolled_cards WHERE roll_id = ?", (roll_id,))
    return cursor.fetchone()


def _get_roll_row_by_card_id(cursor: sqlite3.Cursor, card_id: int) -> Optional[sqlite3.Row]:
    cursor.execute(
        """
        SELECT * FROM rolled_cards
        WHERE original_card_id = ? OR rerolled_card_id = ?
        """,
        (card_id, card_id),
    )
    return cursor.fetchone()


def create_rolled_card(card_id: int, original_roller_id: int) -> int:
    """Create a rolled card entry to track its state."""
    now = datetime.datetime.now().isoformat()
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            """
            INSERT INTO rolled_cards (
                original_card_id,
                rerolled_card_id,
                created_at,
                original_roller_id,
                rerolled,
                being_rerolled,
                attempted_by,
                is_locked
            )
            VALUES (?, NULL, ?, ?, 0, 0, NULL, 0)
            """,
            (card_id, now, original_roller_id),
        )
        return cursor.lastrowid


def get_rolled_card_by_roll_id(roll_id: int) -> Optional[RolledCard]:
    with _managed_connection() as (_, cursor):
        return _row_to_rolled_card(_get_roll_row_by_roll_id(cursor, roll_id))


def get_rolled_card_by_card_id(card_id: int) -> Optional[RolledCard]:
    with _managed_connection() as (_, cursor):
        return _row_to_rolled_card(_get_roll_row_by_card_id(cursor, card_id))


def get_rolled_card(roll_id: int) -> Optional[RolledCard]:
    """Backward-compatible alias for fetching by roll ID."""
    return get_rolled_card_by_roll_id(roll_id)


def update_rolled_card_attempted_by(roll_id: int, username: str) -> None:
    """Add a username to the attempted_by list for a rolled card."""
    with _managed_connection(commit=True) as (_, cursor):
        row = _get_roll_row_by_roll_id(cursor, roll_id)
        if not row:
            return

        attempted_by = row["attempted_by"] or ""
        attempted_list = [u.strip() for u in attempted_by.split(",") if u.strip()]

        if username not in attempted_list:
            attempted_list.append(username)
            new_attempted_by = ", ".join(attempted_list)
            cursor.execute(
                "UPDATE rolled_cards SET attempted_by = ? WHERE roll_id = ?",
                (new_attempted_by, roll_id),
            )


def set_rolled_card_being_rerolled(roll_id: int, being_rerolled: bool) -> None:
    """Set the being_rerolled status for a rolled card."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            "UPDATE rolled_cards SET being_rerolled = ? WHERE roll_id = ?",
            (being_rerolled, roll_id),
        )


def set_rolled_card_rerolled(roll_id: int, new_card_id: Optional[int]) -> None:
    """Mark a rolled card as having been rerolled."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            """
            UPDATE rolled_cards
            SET rerolled = 1,
                being_rerolled = 0,
                rerolled_card_id = ?
            WHERE roll_id = ?
            """,
            (new_card_id, roll_id),
        )


def set_rolled_card_locked(roll_id: int, is_locked: bool) -> None:
    """Set the locked status for a rolled card."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            "UPDATE rolled_cards SET is_locked = ? WHERE roll_id = ?",
            (is_locked, roll_id),
        )


def delete_rolled_card(roll_id: int) -> None:
    """Delete a rolled card entry (use sparingly - prefer reset_rolled_card)."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute("DELETE FROM rolled_cards WHERE roll_id = ?", (roll_id,))


def is_rolled_card_reroll_expired(roll_id: int) -> bool:
    """Check if the reroll time limit (5 minutes) has expired for a rolled card."""
    with _managed_connection() as (_, cursor):
        cursor.execute(
            "SELECT created_at FROM rolled_cards WHERE roll_id = ?",
            (roll_id,),
        )
        result = cursor.fetchone()

    if not result or not result[0]:
        return True

    created_at = datetime.datetime.fromisoformat(result[0])
    time_since_creation = datetime.datetime.now() - created_at
    return time_since_creation.total_seconds() > 5 * 60


def add_character(chat_id: str, name: str, imageb64: str) -> int:
    """Add a new character to the database and generate slot icon."""
    # Generate slot machine icon
    slot_icon_b64 = _generate_slot_icon(imageb64)

    with _managed_connection(commit=True) as (_, cursor):
        if slot_icon_b64:
            cursor.execute(
                "INSERT INTO characters (chat_id, name, imageb64, slot_iconb64) VALUES (?, ?, ?, ?)",
                (str(chat_id), name, imageb64, slot_icon_b64),
            )
            logger.info(f"Added character '{name}' with slot icon to chat {chat_id}")
        else:
            cursor.execute(
                "INSERT INTO characters (chat_id, name, imageb64) VALUES (?, ?, ?)",
                (str(chat_id), name, imageb64),
            )
            logger.info(f"Added character '{name}' to chat {chat_id} (slot icon generation failed)")

        return cursor.lastrowid


def get_character_by_name(chat_id: str, name: str) -> Optional[Character]:
    """Fetch the most recently added character for a chat by case-insensitive name."""
    with _managed_connection() as (_, cursor):
        cursor.execute(
            """
            SELECT * FROM characters
            WHERE chat_id = ? AND LOWER(name) = LOWER(?)
            ORDER BY id DESC
            LIMIT 1
            """,
            (str(chat_id), name),
        )
        row = cursor.fetchone()
        return Character(**row) if row else None


def update_character_image(character_id: int, imageb64: str) -> bool:
    """Update a character's image and regenerate the slot icon when possible."""
    slot_icon_b64 = _generate_slot_icon(imageb64)

    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            """
            UPDATE characters
            SET imageb64 = ?, slot_iconb64 = COALESCE(?, slot_iconb64)
            WHERE id = ?
            """,
            (imageb64, slot_icon_b64, character_id),
        )
        updated = cursor.rowcount > 0

        if updated:
            if slot_icon_b64:
                logger.info("Updated character %s image and regenerated slot icon", character_id)
            else:
                logger.info(
                    "Updated character %s image (slot icon unchanged due to generation failure)",
                    character_id,
                )

        return updated


def delete_characters_by_name(name: str) -> int:
    """Delete all characters with the given name (case-insensitive). Returns count of deleted characters."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute("DELETE FROM characters WHERE LOWER(name) = LOWER(?)", (name,))
        return cursor.rowcount


def get_characters_by_chat(chat_id: str) -> List[Character]:
    """Get all characters for a specific chat."""
    with _managed_connection() as (_, cursor):
        cursor.execute("SELECT * FROM characters WHERE chat_id = ?", (str(chat_id),))
        rows = cursor.fetchall()
        return [Character(**row) for row in rows]


def get_character_by_id(character_id: int) -> Optional[Character]:
    """Get a character by its ID."""
    with _managed_connection() as (_, cursor):
        cursor.execute("SELECT * FROM characters WHERE id = ?", (character_id,))
        row = cursor.fetchone()
        return Character(**row) if row else None


def set_all_claim_balances_to(balance: int) -> int:
    """Set all users' claim balances to the specified amount. Returns the number of affected rows."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute("UPDATE claims SET balance = ?", (balance,))
        return cursor.rowcount


def get_chat_users_and_characters(chat_id: str) -> List[Dict[str, Any]]:
    """Get all users and characters for a specific chat with id, display_name/name, slot_iconb64, and type."""
    with _managed_connection() as (_, cursor):
        cursor.execute(
            """
        SELECT u.user_id as id, u.display_name, u.slot_iconb64, 'user' as type
        FROM chats c
        INNER JOIN users u ON c.user_id = u.user_id
        WHERE c.chat_id = ?
        """,
            (str(chat_id),),
        )
        user_rows = cursor.fetchall()

        cursor.execute(
            """
        SELECT id, name as display_name, slot_iconb64, 'character' as type
        FROM characters
        WHERE chat_id = ?
        """,
            (str(chat_id),),
        )
        character_rows = cursor.fetchall()

    all_items = []
    all_items.extend([dict(row) for row in user_rows])
    all_items.extend([dict(row) for row in character_rows])

    return all_items


def get_next_spin_refresh(user_id: int, chat_id: str) -> Optional[str]:
    """Get the next refresh time for a user's spins. Returns ISO timestamp or None if user not found."""
    with _managed_connection() as (_, cursor):
        cursor.execute(
            "SELECT refresh_timestamp FROM spins WHERE user_id = ? AND chat_id = ?",
            (user_id, str(chat_id)),
        )
        row = cursor.fetchone()

    if not row or not row[0]:
        return None

    refresh_timestamp_str = row[0]
    _, hours_per_refresh = _get_spins_config()

    pdt_tz = ZoneInfo("America/Los_Angeles")

    try:
        if refresh_timestamp_str.endswith("+00:00") or refresh_timestamp_str.endswith("Z"):
            refresh_dt_utc = datetime.datetime.fromisoformat(
                refresh_timestamp_str.replace("Z", "+00:00")
            )
            refresh_dt_pdt = refresh_dt_utc.astimezone(pdt_tz)
        else:
            refresh_dt_naive = datetime.datetime.fromisoformat(
                refresh_timestamp_str.replace("Z", "")
            )
            refresh_dt_pdt = refresh_dt_naive.replace(tzinfo=pdt_tz)

        next_refresh = refresh_dt_pdt + datetime.timedelta(hours=hours_per_refresh)
        return next_refresh.isoformat()
    except (ValueError, TypeError) as e:
        logger.warning(
            f"Invalid refresh_timestamp format for user {user_id} in chat {chat_id}: {e}"
        )
        return None


def get_user_spins(user_id: int, chat_id: str) -> Optional[Spins]:
    """Get the spins record for a user in a specific chat."""
    with _managed_connection() as (_, cursor):
        cursor.execute(
            "SELECT * FROM spins WHERE user_id = ? AND chat_id = ?",
            (user_id, str(chat_id)),
        )
        row = cursor.fetchone()
        return Spins(**row) if row else None


def update_user_spins(user_id: int, chat_id: str, count: int, refresh_timestamp: str) -> bool:
    """Update or insert a spins record for a user in a specific chat."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            """
            INSERT INTO spins (user_id, chat_id, count, refresh_timestamp)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET
                count = excluded.count,
                refresh_timestamp = excluded.refresh_timestamp
            """,
            (user_id, str(chat_id), count, refresh_timestamp),
        )
        return cursor.rowcount > 0


def increment_user_spins(user_id: int, chat_id: str, amount: int = 1) -> Optional[int]:
    """Increment the spin count for a user in a specific chat. Returns new count or None if user not found."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            "UPDATE spins SET count = count + ? WHERE user_id = ? AND chat_id = ?",
            (amount, user_id, str(chat_id)),
        )

        if cursor.rowcount > 0:
            cursor.execute(
                "SELECT count FROM spins WHERE user_id = ? AND chat_id = ?",
                (user_id, str(chat_id)),
            )
            row = cursor.fetchone()
            return row[0] if row else None

        from datetime import datetime

        current_timestamp = datetime.now().isoformat()
        cursor.execute(
            """
            INSERT INTO spins (user_id, chat_id, count, refresh_timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, str(chat_id), amount, current_timestamp),
        )
        return amount


def decrement_user_spins(user_id: int, chat_id: str, amount: int = 1) -> Optional[int]:
    """Decrement the spin count for a user in a specific chat. Returns new count or None if insufficient spins."""
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            "SELECT count FROM spins WHERE user_id = ? AND chat_id = ?",
            (user_id, str(chat_id)),
        )
        row = cursor.fetchone()

        if not row:
            return None

        current_count = row[0]
        if current_count < amount:
            return None

        cursor.execute(
            "UPDATE spins SET count = count - ? WHERE user_id = ? AND chat_id = ?",
            (amount, user_id, str(chat_id)),
        )

        return current_count - amount


def get_or_update_user_spins_with_daily_refresh(user_id: int, chat_id: str) -> int:
    """Get user spins, adding SPINS_PER_REFRESH for each SPINS_REFRESH_HOURS period elapsed. Returns current spins count."""
    with _managed_connection(commit=True) as (_, cursor):
        pdt_tz = ZoneInfo("America/Los_Angeles")
        current_pdt = datetime.datetime.now(pdt_tz)

        cursor.execute(
            "SELECT count, refresh_timestamp FROM spins WHERE user_id = ? AND chat_id = ?",
            (user_id, str(chat_id)),
        )
        row = cursor.fetchone()

        spins_per_refresh, hours_per_refresh = _get_spins_config()

        if not row:
            current_timestamp = current_pdt.isoformat()
            cursor.execute(
                """
                INSERT INTO spins (user_id, chat_id, count, refresh_timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, str(chat_id), spins_per_refresh, current_timestamp),
            )
            return spins_per_refresh

        current_count = row[0]
        refresh_timestamp_str = row[1]

    try:
        if refresh_timestamp_str.endswith("+00:00") or refresh_timestamp_str.endswith("Z"):
            refresh_dt_utc = datetime.datetime.fromisoformat(
                refresh_timestamp_str.replace("Z", "+00:00")
            )
            refresh_dt_pdt = refresh_dt_utc.astimezone(pdt_tz)
        else:
            refresh_dt_naive = datetime.datetime.fromisoformat(
                refresh_timestamp_str.replace("Z", "")
            )
            refresh_dt_pdt = refresh_dt_naive.replace(tzinfo=pdt_tz)

        time_diff = current_pdt - refresh_dt_pdt
        hours_elapsed = time_diff.total_seconds() / 3600
        periods_elapsed = int(hours_elapsed // hours_per_refresh)

        if periods_elapsed <= 0:
            return current_count

        spins_to_add = periods_elapsed * spins_per_refresh
        new_count = current_count + spins_to_add
        new_refresh_dt = refresh_dt_pdt + datetime.timedelta(
            hours=periods_elapsed * hours_per_refresh
        )
        new_timestamp = new_refresh_dt.isoformat()

        with _managed_connection(commit=True) as (_, cursor):
            cursor.execute(
                """
                UPDATE spins SET count = ?, refresh_timestamp = ?
                WHERE user_id = ? AND chat_id = ?
                """,
                (new_count, new_timestamp, user_id, str(chat_id)),
            )

        logger.info(
            f"Added {spins_to_add} spins to user {user_id} in chat {chat_id} ({periods_elapsed} periods of {hours_per_refresh}h elapsed)"
        )
        return new_count
    except (ValueError, TypeError) as e:
        logger.warning(
            f"Invalid refresh_timestamp format for user {user_id} in chat {chat_id}: {e}"
        )
        current_timestamp = datetime.datetime.now(ZoneInfo("America/Los_Angeles")).isoformat()
        new_count = current_count + spins_per_refresh

        with _managed_connection(commit=True) as (_, cursor):
            cursor.execute(
                """
                UPDATE spins SET count = ?, refresh_timestamp = ?
                WHERE user_id = ? AND chat_id = ?
                """,
                (new_count, current_timestamp, user_id, str(chat_id)),
            )
        return new_count


def consume_user_spin(user_id: int, chat_id: str) -> bool:
    """Consume one spin if available. Returns True if successful, False if no spins available."""
    current_count = get_or_update_user_spins_with_daily_refresh(user_id, chat_id)

    if current_count <= 0:
        return False

    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            "UPDATE spins SET count = count - 1 WHERE user_id = ? AND chat_id = ?",
            (user_id, str(chat_id)),
        )
        return cursor.rowcount > 0


def get_thread_id(chat_id: str, type: str = "main") -> Optional[int]:
    """Get the thread_id for a chat_id and type, or None if not set.

    Args:
        chat_id: The chat ID to query.
        type: The thread type ('main' or 'trade'). Defaults to 'main'.
    """
    with _managed_connection() as (_, cursor):
        cursor.execute(
            "SELECT thread_id FROM threads WHERE chat_id = ? AND type = ?",
            (str(chat_id), type),
        )
        row = cursor.fetchone()
        return row[0] if row else None


def set_thread_id(chat_id: str, thread_id: int, type: str = "main") -> bool:
    """Set the thread_id for a chat_id and type. Returns True if successful.

    Args:
        chat_id: The chat ID to set.
        thread_id: The thread ID to set.
        type: The thread type ('main' or 'trade'). Defaults to 'main'.
    """
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            """
            INSERT INTO threads (chat_id, thread_id, type)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id, type) DO UPDATE SET thread_id = excluded.thread_id
            """,
            (str(chat_id), thread_id, type),
        )
        return cursor.rowcount > 0


def clear_thread_ids(chat_id: str) -> bool:
    """Clear all thread_ids for a chat_id. Returns True if successful.

    Args:
        chat_id: The chat ID to clear threads for.
    """
    with _managed_connection(commit=True) as (_, cursor):
        cursor.execute(
            "DELETE FROM threads WHERE chat_id = ?",
            (str(chat_id),),
        )
        return cursor.rowcount > 0


def get_modifier_counts_for_chat(chat_id: str) -> Dict[str, int]:
    """Get the count of each modifier used in cards for a specific chat.

    Args:
        chat_id: The chat ID to get modifier counts for.

    Returns:
        A dictionary mapping modifier strings to their occurrence count.
    """
    with _managed_connection() as (_, cursor):
        cursor.execute(
            "SELECT modifier, COUNT(*) as count FROM cards WHERE chat_id = ? GROUP BY modifier",
            (str(chat_id),),
        )
        return {row["modifier"]: row["count"] for row in cursor.fetchall()}


def get_unique_modifiers(chat_id: str) -> List[str]:
    """Get a list of modifiers used in Unique cards for a specific chat."""
    with _managed_connection() as (_, cursor):
        cursor.execute(
            "SELECT DISTINCT modifier FROM cards WHERE chat_id = ? AND rarity = 'Unique'",
            (str(chat_id),),
        )
        return [row["modifier"] for row in cursor.fetchall()]


def delete_cards(card_ids: List[int]) -> int:
    """Delete multiple cards by ID. Returns number of deleted cards."""
    if not card_ids:
        return 0

    placeholders = ",".join("?" * len(card_ids))
    with _managed_connection() as (conn, cursor):
        cursor.execute(f"DELETE FROM cards WHERE id IN ({placeholders})", tuple(card_ids))
        count = cursor.rowcount
        conn.commit()
        return count


create_tables()
