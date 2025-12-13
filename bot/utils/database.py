import base64
import datetime
import json
import logging
import os
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from alembic import command
from alembic.config import Config
from sqlalchemy import case, func, or_, text
from sqlalchemy.orm import Session, joinedload

from settings.constants import DB_PATH
from utils.image import ImageUtil
from utils.models import (
    CardImageModel,
    CardModel,
    CharacterModel,
    ChatModel,
    ClaimModel,
    MinesweeperGameModel,
    RolledCardModel,
    SetModel,
    SpinsModel,
    ThreadModel,
    UserModel,
    UserRollModel,
)
from utils.schemas import (
    Card,
    CardWithImage,
    Character,
    Claim,
    MinesweeperGame,
    RolledCard,
    Spins,
    User,
)
from utils.session import get_session, initialize_session as _init_session

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

    # Also initialize the SQLAlchemy session with the same configuration
    _init_session(pool_size, timeout_seconds, busy_timeout_ms)

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


# =============================================================================
# ORM to Pydantic Conversion Helpers
# =============================================================================


def _card_model_to_pydantic(card_orm: CardModel) -> Card:
    """Convert a CardModel ORM object to a Card Pydantic model."""
    return Card.from_orm(card_orm)


def _card_model_to_pydantic_with_image(card_orm: CardModel) -> Optional[CardWithImage]:
    """Convert a CardModel ORM object (with eager-loaded image) to a CardWithImage Pydantic model."""
    return CardWithImage.from_orm(card_orm)


def _user_model_to_pydantic(user_orm: UserModel) -> User:
    """Convert a UserModel ORM object to a User Pydantic model."""
    return User.from_orm(user_orm)


def _rolled_card_model_to_pydantic(rolled_orm: RolledCardModel) -> RolledCard:
    """Convert a RolledCardModel ORM object to a RolledCard Pydantic model."""
    return RolledCard.from_orm(rolled_orm)


def _character_model_to_pydantic(char_orm: CharacterModel) -> Character:
    """Convert a CharacterModel ORM object to a Character Pydantic model."""
    return Character.from_orm(char_orm)


def _spins_model_to_pydantic(spins_orm: SpinsModel) -> Spins:
    """Convert a SpinsModel ORM object to a Spins Pydantic model."""
    return Spins.from_orm(spins_orm)


def _minesweeper_model_to_pydantic(game_orm: MinesweeperGameModel) -> MinesweeperGame:
    """Convert a MinesweeperGameModel ORM object to a MinesweeperGame Pydantic model."""
    return MinesweeperGame.from_orm(game_orm)


def _get_alembic_config() -> Config:
    """Build an Alembic configuration pointing at the project's migration setup."""
    config = Config(ALEMBIC_INI_PATH)
    config.set_main_option("script_location", ALEMBIC_SCRIPT_LOCATION)
    config.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH}")
    return config


def _has_table(table_name: str) -> bool:
    with get_session() as session:
        result = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name = :table_name"),
            {"table_name": table_name},
        ).fetchone()
        return result is not None


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

    with get_session(commit=True) as session:
        # Create card model
        card = CardModel(
            base_name=base_name,
            modifier=modifier,
            rarity=rarity,
            chat_id=chat_id,
            created_at=now,
            source_type=source_type,
            source_id=source_id,
            set_id=set_id,
        )
        session.add(card)
        session.flush()  # Get the card ID

        # Create associated image record if available
        if image_b64 or image_thumb_b64:
            card_image = CardImageModel(
                card_id=card.id,
                image_b64=image_b64,
                image_thumb_b64=image_thumb_b64,
            )
            session.add(card_image)

        return card.id


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
    with get_session(commit=True) as session:
        existing = session.query(SetModel).filter(SetModel.id == set_id).first()
        if existing:
            existing.name = name
        else:
            new_set = SetModel(id=set_id, name=name)
            session.add(new_set)


def get_set_id_by_name(name: str) -> Optional[int]:
    """Get the set ID for a given set name."""
    with get_session() as session:
        result = session.query(SetModel.id).filter(SetModel.name == name).first()
        return result[0] if result else None


def try_claim_card(card_id: int, owner: str, user_id: Optional[int] = None) -> bool:
    """Attempt to claim a card for a user without touching claim balances."""
    with get_session(commit=True) as session:
        card = (
            session.query(CardModel)
            .filter(
                CardModel.id == card_id,
                CardModel.owner.is_(None),
            )
            .first()
        )

        if card is None:
            return False

        card.owner = owner
        if user_id is not None:
            card.user_id = user_id
        return True


def _ensure_claim_row_orm(session: Session, user_id: int, chat_id: str) -> ClaimModel:
    """Ensure a claim row exists and return it."""
    claim = (
        session.query(ClaimModel)
        .filter(
            ClaimModel.user_id == user_id,
            ClaimModel.chat_id == chat_id,
        )
        .first()
    )

    if claim is None:
        claim = ClaimModel(user_id=user_id, chat_id=chat_id, balance=1)
        session.add(claim)
        session.flush()

    return claim


def get_claim_balance(user_id: int, chat_id: str) -> int:
    with get_session(commit=True) as session:
        claim = _ensure_claim_row_orm(session, user_id, str(chat_id))
        return claim.balance


def increment_claim_balance(user_id: int, chat_id: str, amount: int = 1) -> int:
    if amount <= 0:
        return get_claim_balance(user_id, chat_id)

    with get_session(commit=True) as session:
        claim = _ensure_claim_row_orm(session, user_id, str(chat_id))
        claim.balance += amount
        return claim.balance


def reduce_claim_points(user_id: int, chat_id: str, amount: int = 1) -> Optional[int]:
    """
    Attempt to reduce claim points for a user.

    Returns the remaining balance if successful, or None if insufficient balance.
    """
    if amount <= 0:
        return get_claim_balance(user_id, chat_id)

    with get_session(commit=True) as session:
        claim = _ensure_claim_row_orm(session, user_id, str(chat_id))
        if claim.balance < amount:
            return None  # Insufficient balance

        claim.balance -= amount
        if claim.balance < 0:
            claim.balance = 0
        return claim.balance


def get_username_for_user_id(user_id: int) -> Optional[str]:
    """Return the username associated with a user_id, falling back to card ownership."""
    with get_session() as session:
        user = session.query(UserModel).filter(UserModel.user_id == user_id).first()
        if user and user.username:
            return user.username

        # Fallback: check card ownership
        card = (
            session.query(CardModel.owner)
            .filter(CardModel.user_id == user_id, CardModel.owner.isnot(None))
            .order_by(CardModel.created_at.desc())
            .first()
        )
        if card and card[0]:
            return card[0]
        return None


def get_user_id_by_username(username: str) -> Optional[int]:
    """Resolve a username to a user_id if available."""
    with get_session() as session:
        user = (
            session.query(UserModel)
            .filter(func.lower(UserModel.username) == func.lower(username))
            .first()
        )
        if user:
            return user.user_id

        # Fallback: check card ownership
        card = (
            session.query(CardModel.user_id)
            .filter(
                func.lower(CardModel.owner) == func.lower(username),
                CardModel.user_id.isnot(None),
            )
            .order_by(CardModel.created_at.desc())
            .first()
        )
        if card and card[0] is not None:
            return int(card[0])
        return None


def get_most_frequent_chat_id_for_user(user_id: int) -> Optional[str]:
    """
    Get the most frequently used chat_id among a user's cards.

    Args:
        user_id: The user's ID

    Returns:
        The most frequently used chat_id, or None if user has no cards
    """
    with get_session() as session:
        result = (
            session.query(CardModel.chat_id, func.count(CardModel.id).label("count"))
            .filter(CardModel.user_id == user_id, CardModel.chat_id.isnot(None))
            .group_by(CardModel.chat_id)
            .order_by(func.count(CardModel.id).desc())
            .first()
        )
        if result and result[0]:
            return str(result[0])
        return None


def _build_rarity_order_case():
    """Build a CASE expression for ordering by rarity."""
    return case(
        (CardModel.rarity == "Unique", 1),
        (CardModel.rarity == "Legendary", 2),
        (CardModel.rarity == "Epic", 3),
        (CardModel.rarity == "Rare", 4),
        else_=5,
    )


def get_user_collection(user_id: int, chat_id: Optional[str] = None) -> List[Card]:
    """Get all cards owned by a user (by user_id), optionally scoped to a chat.

    Returns:
        List[Card]: List of Card objects owned by the user
    """
    username = get_username_for_user_id(user_id)

    with get_session() as session:
        # Build owner conditions (user_id OR owner matches)
        owner_conditions = [CardModel.user_id == user_id]
        if username:
            owner_conditions.append(func.lower(CardModel.owner) == func.lower(username))

        query = session.query(CardModel).filter(or_(*owner_conditions))

        if chat_id is not None:
            query = query.filter(CardModel.chat_id == str(chat_id))

        query = query.order_by(_build_rarity_order_case(), CardModel.base_name, CardModel.modifier)

        return [_card_model_to_pydantic(card) for card in query.all()]


def get_user_card_count(user_id: int, chat_id: Optional[str] = None) -> int:
    """Get count of cards owned by a user (by user_id), optionally scoped to a chat."""
    username = get_username_for_user_id(user_id)

    with get_session() as session:
        owner_conditions = [CardModel.user_id == user_id]
        if username:
            owner_conditions.append(func.lower(CardModel.owner) == func.lower(username))

        query = session.query(func.count(CardModel.id)).filter(or_(*owner_conditions))

        if chat_id is not None:
            query = query.filter(CardModel.chat_id == str(chat_id))

        return query.scalar() or 0


def get_user_cards_by_rarity(
    user_id: int,
    username: Optional[str],
    rarity: str,
    chat_id: Optional[str] = None,
    limit: Optional[int] = None,
    unlocked: bool = False,
) -> List[Card]:
    """Return cards owned by the user for a specific rarity, optionally limited in count."""
    owner_conditions = []

    if user_id is not None:
        owner_conditions.append(CardModel.user_id == user_id)

    if username:
        owner_conditions.append(func.lower(CardModel.owner) == func.lower(username))

    if not owner_conditions:
        return []

    with get_session() as session:
        query = session.query(CardModel).filter(
            or_(*owner_conditions),
            CardModel.rarity == rarity,
        )

        if chat_id is not None:
            query = query.filter(CardModel.chat_id == str(chat_id))

        if unlocked:
            query = query.filter(CardModel.locked == False)

        query = query.order_by(func.coalesce(CardModel.created_at, ""), CardModel.id)

        if limit is not None:
            query = query.limit(limit)

        return [_card_model_to_pydantic(card) for card in query.all()]


def get_all_cards(chat_id: Optional[str] = None) -> List[Card]:
    """Get all cards that have an owner, optionally filtered by chat."""
    with get_session() as session:
        query = session.query(CardModel).filter(CardModel.owner.isnot(None))

        if chat_id is not None:
            query = query.filter(CardModel.chat_id == str(chat_id))

        query = query.order_by(_build_rarity_order_case(), CardModel.base_name, CardModel.modifier)

        return [_card_model_to_pydantic(card) for card in query.all()]


def get_card(card_id) -> Optional[CardWithImage]:
    """Get a card by its ID."""
    with get_session() as session:
        card_orm = (
            session.query(CardModel)
            .options(joinedload(CardModel.image))
            .filter(CardModel.id == card_id)
            .first()
        )
        if card_orm is None:
            return None
        return _card_model_to_pydantic_with_image(card_orm)


def get_card_image(card_id: int) -> str | None:
    """Get the base64 encoded image for a card."""
    with get_session() as session:
        card_image = session.query(CardImageModel).filter(CardImageModel.card_id == card_id).first()
        return card_image.image_b64 if card_image else None


def get_card_images_batch(card_ids: List[int]) -> dict[int, str]:
    """Get thumbnail base64 images for multiple cards, generating them when missing."""
    if not card_ids:
        return {}

    with get_session(commit=True) as session:
        card_images = (
            session.query(CardImageModel).filter(CardImageModel.card_id.in_(card_ids)).all()
        )

        fetched: dict[int, str] = {}
        for card_image in card_images:
            cid = card_image.card_id
            thumb = card_image.image_thumb_b64
            full = card_image.image_b64

            if thumb:
                fetched[cid] = thumb
                continue

            if not full:
                continue

            try:
                image_bytes = base64.b64decode(full)
                thumb_bytes = ImageUtil.compress_to_fraction(image_bytes, scale_factor=1 / 4)
                thumb_b64 = base64.b64encode(thumb_bytes).decode("utf-8")
                card_image.image_thumb_b64 = thumb_b64
                fetched[cid] = thumb_b64
            except Exception as exc:
                logger.warning(
                    "Failed to generate thumbnail during batch fetch for card %s: %s",
                    cid,
                    exc,
                )

        # Return in original order
        ordered: dict[int, str] = {}
        for cid in card_ids:
            image = fetched.get(cid)
            if image is not None:
                ordered[cid] = image
        return ordered


def get_total_cards_count() -> int:
    """Get the total number of cards ever generated."""
    with get_session() as session:
        count = session.query(func.count(CardModel.id)).filter(CardModel.owner.isnot(None)).scalar()
        return count or 0


def get_user_stats(username):
    """Get card statistics for a user."""
    with get_session() as session:
        owned_count = (
            session.query(func.count(CardModel.id)).filter(CardModel.owner == username).scalar()
            or 0
        )

        rarities = ["Unique", "Legendary", "Epic", "Rare", "Common"]
        rarity_counts = {}
        for rarity in rarities:
            count = (
                session.query(func.count(CardModel.id))
                .filter(CardModel.owner == username, CardModel.rarity == rarity)
                .scalar()
                or 0
            )
            rarity_counts[rarity] = count

    total_count = get_total_cards_count()

    return {"owned": owned_count, "total": total_count, "rarities": rarity_counts}


def get_all_users_with_cards(chat_id: Optional[str] = None):
    """Get all unique users who have claimed cards, optionally scoped to a chat."""
    with get_session() as session:
        query = session.query(CardModel.owner).filter(CardModel.owner.isnot(None)).distinct()

        if chat_id is not None:
            query = query.filter(CardModel.chat_id == str(chat_id))

        query = query.order_by(CardModel.owner)
        return [row[0] for row in query.all()]


def get_last_roll_time(user_id: int, chat_id: str):
    """Get the last roll timestamp for a user within a specific chat."""
    with get_session() as session:
        roll = (
            session.query(UserRollModel)
            .filter(
                UserRollModel.user_id == user_id,
                UserRollModel.chat_id == str(chat_id),
            )
            .first()
        )
        if roll and roll.last_roll_timestamp:
            return datetime.datetime.fromisoformat(roll.last_roll_timestamp)
        return None


def can_roll(user_id: int, chat_id: str):
    """Check if a user can roll (24 hours since last roll) within a chat."""
    last_roll_time = get_last_roll_time(user_id, chat_id)
    if last_roll_time is None:
        return True

    time_since_last_roll = datetime.datetime.now() - last_roll_time
    return time_since_last_roll.total_seconds() >= 24 * 60 * 60


def record_roll(user_id: int, chat_id: str):
    """Record a user's roll timestamp for a specific chat."""
    now = datetime.datetime.now().isoformat()
    with get_session(commit=True) as session:
        roll = (
            session.query(UserRollModel)
            .filter(
                UserRollModel.user_id == user_id,
                UserRollModel.chat_id == str(chat_id),
            )
            .first()
        )

        if roll:
            roll.last_roll_timestamp = now
        else:
            roll = UserRollModel(
                user_id=user_id,
                chat_id=str(chat_id),
                last_roll_timestamp=now,
            )
            session.add(roll)


def swap_card_owners(card_id1, card_id2) -> bool:
    """Swap the owners of two cards."""
    try:
        with get_session(commit=True) as session:
            card1 = session.query(CardModel).filter(CardModel.id == card_id1).first()
            if not card1:
                return False

            card2 = session.query(CardModel).filter(CardModel.id == card_id2).first()
            if not card2:
                return False

            # Swap owners and user_ids
            card1.owner, card2.owner = card2.owner, card1.owner
            card1.user_id, card2.user_id = card2.user_id, card1.user_id
            return True
    except Exception:
        return False


def set_card_owner(card_id: int, owner: str, user_id: Optional[int] = None) -> bool:
    """Set the owner and optional user_id for a card without affecting claim balances."""
    with get_session(commit=True) as session:
        card = session.query(CardModel).filter(CardModel.id == card_id).first()
        if not card:
            return False
        card.owner = owner
        card.user_id = user_id
        return True


def update_card_file_id(card_id, file_id) -> None:
    """Update the Telegram file_id for a card."""
    with get_session(commit=True) as session:
        card = session.query(CardModel).filter(CardModel.id == card_id).first()
        if card:
            card.file_id = file_id
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

    with get_session(commit=True) as session:
        # Update or create card_images record
        card_image = session.query(CardImageModel).filter(CardImageModel.card_id == card_id).first()
        if card_image:
            card_image.image_b64 = image_b64
            card_image.image_thumb_b64 = image_thumb_b64
        else:
            card_image = CardImageModel(
                card_id=card_id,
                image_b64=image_b64,
                image_thumb_b64=image_thumb_b64,
            )
            session.add(card_image)

        # Clear file_id since we have a new image
        card = session.query(CardModel).filter(CardModel.id == card_id).first()
        if card:
            card.file_id = None

    logger.info(f"Updated image for card {card_id}, cleared file_id")


def set_card_locked(card_id: int, is_locked: bool) -> None:
    """Set the locked status for a card."""
    with get_session(commit=True) as session:
        card = session.query(CardModel).filter(CardModel.id == card_id).first()
        if card:
            card.locked = is_locked
    logger.info(f"Set locked={is_locked} for card {card_id}")


def clear_all_file_ids():
    """Clear all file_ids from all cards (set to NULL)."""
    with get_session(commit=True) as session:
        affected_rows = session.query(CardModel).update({CardModel.file_id: None})
    logger.info(f"Cleared file_ids for {affected_rows} cards")
    return affected_rows


def nullify_card_owner(card_id) -> bool:
    """Set card owner to NULL (for rerolls/burns) instead of deleting."""
    with get_session(commit=True) as session:
        card = session.query(CardModel).filter(CardModel.id == card_id).first()
        if not card:
            logger.info(f"Nullified owner for card {card_id}: False")
            return False
        card.owner = None
        card.user_id = None
    logger.info(f"Nullified owner for card {card_id}: True")
    return True


def delete_card(card_id) -> bool:
    """Delete a card from the database (use sparingly - prefer nullify_card_owner)."""
    with get_session(commit=True) as session:
        deleted = session.query(CardModel).filter(CardModel.id == card_id).delete()
    logger.info(f"Deleted card {card_id}: {deleted > 0}")
    return deleted > 0


def upsert_user(
    user_id: int,
    username: str,
    display_name: Optional[str] = None,
    profile_imageb64: Optional[str] = None,
) -> None:
    """Insert or update a user record."""
    with get_session(commit=True) as session:
        user = session.query(UserModel).filter(UserModel.user_id == user_id).first()
        if user:
            user.username = username
            if display_name is not None:
                user.display_name = display_name
            if profile_imageb64 is not None:
                user.profile_imageb64 = profile_imageb64
        else:
            user = UserModel(
                user_id=user_id,
                username=username,
                display_name=display_name,
                profile_imageb64=profile_imageb64,
            )
            session.add(user)


def update_user_profile(user_id: int, display_name: str, profile_imageb64: str) -> bool:
    """Update the display name and profile image for a user, and generate slot icon."""
    # Generate slot machine icon
    slot_icon_b64 = _generate_slot_icon(profile_imageb64)

    with get_session(commit=True) as session:
        user = session.query(UserModel).filter(UserModel.user_id == user_id).first()
        if not user:
            return False

        user.display_name = display_name
        user.profile_imageb64 = profile_imageb64
        if slot_icon_b64:
            user.slot_iconb64 = slot_icon_b64
            logger.info(f"Updated user profile and slot icon for user {user_id}")
        else:
            logger.info(f"Updated user profile for user {user_id} (slot icon generation failed)")

        return True


def get_user(user_id: int) -> Optional[User]:
    """Fetch a user record by ID."""
    with get_session() as session:
        user_orm = session.query(UserModel).filter(UserModel.user_id == user_id).first()
        return _user_model_to_pydantic(user_orm) if user_orm else None


def user_exists(user_id: int) -> bool:
    """Check whether a user exists in the users table."""
    with get_session() as session:
        return session.query(UserModel).filter(UserModel.user_id == user_id).first() is not None


def get_all_chat_users_with_profile(chat_id: str) -> List[User]:
    """Return all users enrolled in the chat with stored profile images and display names."""
    with get_session() as session:
        users = (
            session.query(UserModel)
            .join(ChatModel, ChatModel.user_id == UserModel.user_id)
            .filter(
                ChatModel.chat_id == str(chat_id),
                UserModel.profile_imageb64.isnot(None),
                func.trim(UserModel.profile_imageb64) != "",
                UserModel.display_name.isnot(None),
                func.trim(UserModel.display_name) != "",
            )
            .all()
        )
        return [_user_model_to_pydantic(u) for u in users]


def get_random_chat_user_with_profile(chat_id: str) -> Optional[User]:
    """Return a random user enrolled in the chat with a stored profile image."""
    with get_session() as session:
        user = (
            session.query(UserModel)
            .join(ChatModel, ChatModel.user_id == UserModel.user_id)
            .filter(
                ChatModel.chat_id == str(chat_id),
                UserModel.profile_imageb64.isnot(None),
                func.trim(UserModel.profile_imageb64) != "",
                UserModel.display_name.isnot(None),
                func.trim(UserModel.display_name) != "",
            )
            .order_by(func.random())
            .first()
        )
        return _user_model_to_pydantic(user) if user else None


def add_user_to_chat(chat_id: str, user_id: int) -> bool:
    """Add a user to a chat; returns True if inserted."""
    with get_session(commit=True) as session:
        existing = (
            session.query(ChatModel)
            .filter(
                ChatModel.chat_id == str(chat_id),
                ChatModel.user_id == user_id,
            )
            .first()
        )
        if existing:
            return False
        chat = ChatModel(chat_id=str(chat_id), user_id=user_id)
        session.add(chat)
        return True


def remove_user_from_chat(chat_id: str, user_id: int) -> bool:
    """Remove a user from a chat; returns True if a row was deleted."""
    with get_session(commit=True) as session:
        deleted = (
            session.query(ChatModel)
            .filter(
                ChatModel.chat_id == str(chat_id),
                ChatModel.user_id == user_id,
            )
            .delete()
        )
        return deleted > 0


def is_user_in_chat(chat_id: str, user_id: int) -> bool:
    """Check whether a user is enrolled in a chat."""
    with get_session() as session:
        return (
            session.query(ChatModel)
            .filter(
                ChatModel.chat_id == str(chat_id),
                ChatModel.user_id == user_id,
            )
            .first()
            is not None
        )


def get_all_chat_users(chat_id: str) -> List[int]:
    """Get all user IDs enrolled in a specific chat."""
    with get_session() as session:
        chats = session.query(ChatModel.user_id).filter(ChatModel.chat_id == str(chat_id)).all()
        return [c[0] for c in chats]


def create_rolled_card(card_id: int, original_roller_id: int) -> int:
    """Create a rolled card entry to track its state."""
    now = datetime.datetime.now().isoformat()
    with get_session(commit=True) as session:
        rolled = RolledCardModel(
            original_card_id=card_id,
            created_at=now,
            original_roller_id=original_roller_id,
            rerolled=False,
            being_rerolled=False,
            is_locked=False,
        )
        session.add(rolled)
        session.flush()
        return rolled.roll_id


def get_rolled_card_by_roll_id(roll_id: int) -> Optional[RolledCard]:
    with get_session() as session:
        rolled = session.query(RolledCardModel).filter(RolledCardModel.roll_id == roll_id).first()
        return _rolled_card_model_to_pydantic(rolled) if rolled else None


def get_rolled_card_by_card_id(card_id: int) -> Optional[RolledCard]:
    with get_session() as session:
        rolled = (
            session.query(RolledCardModel)
            .filter(
                or_(
                    RolledCardModel.original_card_id == card_id,
                    RolledCardModel.rerolled_card_id == card_id,
                )
            )
            .first()
        )
        return _rolled_card_model_to_pydantic(rolled) if rolled else None


def get_rolled_card(roll_id: int) -> Optional[RolledCard]:
    """Backward-compatible alias for fetching by roll ID."""
    return get_rolled_card_by_roll_id(roll_id)


def update_rolled_card_attempted_by(roll_id: int, username: str) -> None:
    """Add a username to the attempted_by list for a rolled card."""
    with get_session(commit=True) as session:
        rolled = session.query(RolledCardModel).filter(RolledCardModel.roll_id == roll_id).first()
        if not rolled:
            return

        attempted_by = rolled.attempted_by or ""
        attempted_list = [u.strip() for u in attempted_by.split(",") if u.strip()]

        if username not in attempted_list:
            attempted_list.append(username)
            rolled.attempted_by = ", ".join(attempted_list)


def set_rolled_card_being_rerolled(roll_id: int, being_rerolled: bool) -> None:
    """Set the being_rerolled status for a rolled card."""
    with get_session(commit=True) as session:
        rolled = session.query(RolledCardModel).filter(RolledCardModel.roll_id == roll_id).first()
        if rolled:
            rolled.being_rerolled = being_rerolled


def set_rolled_card_rerolled(roll_id: int, new_card_id: Optional[int]) -> None:
    """Mark a rolled card as having been rerolled."""
    with get_session(commit=True) as session:
        rolled = session.query(RolledCardModel).filter(RolledCardModel.roll_id == roll_id).first()
        if rolled:
            rolled.rerolled = True
            rolled.being_rerolled = False
            rolled.rerolled_card_id = new_card_id


def set_rolled_card_locked(roll_id: int, is_locked: bool) -> None:
    """Set the locked status for a rolled card."""
    with get_session(commit=True) as session:
        rolled = session.query(RolledCardModel).filter(RolledCardModel.roll_id == roll_id).first()
        if rolled:
            rolled.is_locked = is_locked


def delete_rolled_card(roll_id: int) -> None:
    """Delete a rolled card entry (use sparingly - prefer reset_rolled_card)."""
    with get_session(commit=True) as session:
        session.query(RolledCardModel).filter(RolledCardModel.roll_id == roll_id).delete()


def is_rolled_card_reroll_expired(roll_id: int) -> bool:
    """Check if the reroll time limit (5 minutes) has expired for a rolled card."""
    with get_session() as session:
        rolled = session.query(RolledCardModel).filter(RolledCardModel.roll_id == roll_id).first()
        if not rolled or not rolled.created_at:
            return True

        created_at = datetime.datetime.fromisoformat(rolled.created_at)
        time_since_creation = datetime.datetime.now() - created_at
        return time_since_creation.total_seconds() > 5 * 60


def add_character(chat_id: str, name: str, imageb64: str) -> int:
    """Add a new character to the database and generate slot icon."""
    # Generate slot machine icon
    slot_icon_b64 = _generate_slot_icon(imageb64)

    with get_session(commit=True) as session:
        character = CharacterModel(
            chat_id=str(chat_id),
            name=name,
            imageb64=imageb64,
            slot_iconb64=slot_icon_b64,
        )
        session.add(character)
        session.flush()

        if slot_icon_b64:
            logger.info(f"Added character '{name}' with slot icon to chat {chat_id}")
        else:
            logger.info(f"Added character '{name}' to chat {chat_id} (slot icon generation failed)")

        return character.id


def get_character_by_name(chat_id: str, name: str) -> Optional[Character]:
    """Fetch the most recently added character for a chat by case-insensitive name."""
    with get_session() as session:
        character = (
            session.query(CharacterModel)
            .filter(
                CharacterModel.chat_id == str(chat_id),
                func.lower(CharacterModel.name) == func.lower(name),
            )
            .order_by(CharacterModel.id.desc())
            .first()
        )
        return _character_model_to_pydantic(character) if character else None


def update_character_image(character_id: int, imageb64: str) -> bool:
    """Update a character's image and regenerate the slot icon when possible."""
    slot_icon_b64 = _generate_slot_icon(imageb64)

    with get_session(commit=True) as session:
        character = session.query(CharacterModel).filter(CharacterModel.id == character_id).first()
        if not character:
            return False

        character.imageb64 = imageb64
        if slot_icon_b64:
            character.slot_iconb64 = slot_icon_b64
            logger.info("Updated character %s image and regenerated slot icon", character_id)
        else:
            logger.info(
                "Updated character %s image (slot icon unchanged due to generation failure)",
                character_id,
            )
        return True


def delete_characters_by_name(name: str) -> int:
    """Delete all characters with the given name (case-insensitive). Returns count of deleted characters."""
    with get_session(commit=True) as session:
        deleted = (
            session.query(CharacterModel)
            .filter(func.lower(CharacterModel.name) == func.lower(name))
            .delete(synchronize_session=False)
        )
        return deleted


def get_characters_by_chat(chat_id: str) -> List[Character]:
    """Get all characters for a specific chat."""
    with get_session() as session:
        characters = (
            session.query(CharacterModel).filter(CharacterModel.chat_id == str(chat_id)).all()
        )
        return [_character_model_to_pydantic(c) for c in characters]


def get_character_by_id(character_id: int) -> Optional[Character]:
    """Get a character by its ID."""
    with get_session() as session:
        character = session.query(CharacterModel).filter(CharacterModel.id == character_id).first()
        return _character_model_to_pydantic(character) if character else None


def set_all_claim_balances_to(balance: int) -> int:
    """Set all users' claim balances to the specified amount. Returns the number of affected rows."""
    with get_session(commit=True) as session:
        affected = session.query(ClaimModel).update({ClaimModel.balance: balance})
        return affected


def get_chat_users_and_characters(chat_id: str) -> List[Dict[str, Any]]:
    """Get all users and characters for a specific chat with id, display_name/name, slot_iconb64, and type."""
    with get_session() as session:
        # Get users
        user_results = (
            session.query(
                UserModel.user_id.label("id"),
                UserModel.display_name,
                UserModel.slot_iconb64,
            )
            .join(ChatModel, ChatModel.user_id == UserModel.user_id)
            .filter(ChatModel.chat_id == str(chat_id))
            .all()
        )

        # Get characters
        char_results = (
            session.query(
                CharacterModel.id,
                CharacterModel.name.label("display_name"),
                CharacterModel.slot_iconb64,
            )
            .filter(CharacterModel.chat_id == str(chat_id))
            .all()
        )

    all_items = []
    for row in user_results:
        all_items.append(
            {
                "id": row.id,
                "display_name": row.display_name,
                "slot_iconb64": row.slot_iconb64,
                "type": "user",
            }
        )
    for row in char_results:
        all_items.append(
            {
                "id": row.id,
                "display_name": row.display_name,
                "slot_iconb64": row.slot_iconb64,
                "type": "character",
            }
        )

    return all_items


def get_next_spin_refresh(user_id: int, chat_id: str) -> Optional[str]:
    """Get the next refresh time for a user's spins. Returns ISO timestamp or None if user not found."""
    with get_session() as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )

    if not spins or not spins.refresh_timestamp:
        return None

    refresh_timestamp_str = spins.refresh_timestamp
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
    with get_session() as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )
        return _spins_model_to_pydantic(spins) if spins else None


def update_user_spins(user_id: int, chat_id: str, count: int, refresh_timestamp: str) -> bool:
    """Update or insert a spins record for a user in a specific chat."""
    with get_session(commit=True) as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )

        if spins:
            spins.count = count
            spins.refresh_timestamp = refresh_timestamp
        else:
            spins = SpinsModel(
                user_id=user_id,
                chat_id=str(chat_id),
                count=count,
                refresh_timestamp=refresh_timestamp,
            )
            session.add(spins)
        return True


def increment_user_spins(user_id: int, chat_id: str, amount: int = 1) -> Optional[int]:
    """Increment the spin count for a user in a specific chat. Returns new count or None if user not found."""
    with get_session(commit=True) as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )

        if spins:
            spins.count += amount
            return spins.count

        # Create new record if doesn't exist
        current_timestamp = datetime.datetime.now().isoformat()
        spins = SpinsModel(
            user_id=user_id,
            chat_id=str(chat_id),
            count=amount,
            refresh_timestamp=current_timestamp,
        )
        session.add(spins)
        return amount


def decrement_user_spins(user_id: int, chat_id: str, amount: int = 1) -> Optional[int]:
    """Decrement the spin count for a user in a specific chat. Returns new count or None if insufficient spins."""
    with get_session(commit=True) as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )

        if not spins:
            return None

        if spins.count < amount:
            return None

        spins.count -= amount
        return spins.count


def get_or_update_user_spins_with_daily_refresh(user_id: int, chat_id: str) -> int:
    """Get user spins, adding SPINS_PER_REFRESH for each SPINS_REFRESH_HOURS period elapsed. Returns current spins count."""
    pdt_tz = ZoneInfo("America/Los_Angeles")
    current_pdt = datetime.datetime.now(pdt_tz)
    spins_per_refresh, hours_per_refresh = _get_spins_config()

    with get_session(commit=True) as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )

        if not spins:
            current_timestamp = current_pdt.isoformat()
            new_spins = SpinsModel(
                user_id=user_id,
                chat_id=str(chat_id),
                count=spins_per_refresh,
                refresh_timestamp=current_timestamp,
            )
            session.add(new_spins)
            return spins_per_refresh

        current_count = spins.count
        refresh_timestamp_str = spins.refresh_timestamp

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

            spins.count = new_count
            spins.refresh_timestamp = new_timestamp

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
            spins.count = new_count
            spins.refresh_timestamp = current_timestamp
            return new_count


def consume_user_spin(user_id: int, chat_id: str) -> bool:
    """Consume one spin if available. Returns True if successful, False if no spins available."""
    current_count = get_or_update_user_spins_with_daily_refresh(user_id, chat_id)

    if current_count <= 0:
        return False

    with get_session(commit=True) as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )
        if spins and spins.count > 0:
            spins.count -= 1
            return True
        return False


def get_thread_id(chat_id: str, type: str = "main") -> Optional[int]:
    """Get the thread_id for a chat_id and type, or None if not set.

    Args:
        chat_id: The chat ID to query.
        type: The thread type ('main' or 'trade'). Defaults to 'main'.
    """
    with get_session() as session:
        thread = (
            session.query(ThreadModel)
            .filter(
                ThreadModel.chat_id == str(chat_id),
                ThreadModel.type == type,
            )
            .first()
        )
        return thread.thread_id if thread else None


def set_thread_id(chat_id: str, thread_id: int, type: str = "main") -> bool:
    """Set the thread_id for a chat_id and type. Returns True if successful.

    Args:
        chat_id: The chat ID to set.
        thread_id: The thread ID to set.
        type: The thread type ('main' or 'trade'). Defaults to 'main'.
    """
    with get_session(commit=True) as session:
        # Try to find existing thread
        existing = (
            session.query(ThreadModel)
            .filter(
                ThreadModel.chat_id == str(chat_id),
                ThreadModel.type == type,
            )
            .first()
        )

        if existing:
            existing.thread_id = thread_id
        else:
            new_thread = ThreadModel(
                chat_id=str(chat_id),
                thread_id=thread_id,
                type=type,
            )
            session.add(new_thread)
        return True


def clear_thread_ids(chat_id: str) -> bool:
    """Clear all thread_ids for a chat_id. Returns True if successful.

    Args:
        chat_id: The chat ID to clear threads for.
    """
    with get_session(commit=True) as session:
        deleted = (
            session.query(ThreadModel)
            .filter(
                ThreadModel.chat_id == str(chat_id),
            )
            .delete()
        )
        return deleted > 0


def get_modifier_counts_for_chat(chat_id: str) -> Dict[str, int]:
    """Get the count of each modifier used in cards for a specific chat.

    Args:
        chat_id: The chat ID to get modifier counts for.

    Returns:
        A dictionary mapping modifier strings to their occurrence count.
    """
    with get_session() as session:
        results = (
            session.query(CardModel.modifier, func.count(CardModel.id).label("count"))
            .filter(CardModel.chat_id == str(chat_id))
            .group_by(CardModel.modifier)
            .all()
        )
        return {row[0]: row[1] for row in results if row[0] is not None}


def get_unique_modifiers(chat_id: str) -> List[str]:
    """Get a list of modifiers used in Unique cards for a specific chat."""
    with get_session() as session:
        results = (
            session.query(CardModel.modifier)
            .filter(
                CardModel.chat_id == str(chat_id),
                CardModel.rarity == "Unique",
            )
            .distinct()
            .all()
        )
        return [row[0] for row in results if row[0] is not None]


def delete_cards(card_ids: List[int]) -> int:
    """Delete multiple cards by ID. Returns number of deleted cards."""
    if not card_ids:
        return 0

    with get_session(commit=True) as session:
        deleted = (
            session.query(CardModel)
            .filter(CardModel.id.in_(card_ids))
            .delete(synchronize_session=False)
        )
        return deleted


create_tables()
