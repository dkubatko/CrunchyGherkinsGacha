"""
Minesweeper game logic and database interactions.

This module handles:
- Mine field generation (3x3 grid with configurable bomb count)
- Game state management
- Database operations for minesweeper games
"""

import base64
import json
import logging
import os
import random
import sys
from datetime import datetime, timezone
from typing import Optional, List, Tuple

from utils.schemas import MinesweeperGame
from utils.session import get_session
from utils.models import MinesweeperGameModel
from utils import rolling
from settings.constants import MINESWEEPER_MINE_COUNT, MINESWEEPER_CLAIM_POINT_COUNT

logger = logging.getLogger(__name__)

# Constants
GRID_SIZE = 9  # 3x3 grid
SAFE_REVEALS_REQUIRED = 3  # Number of safe cells to reveal to win
DEBUG_MODE = "--debug" in sys.argv  # Keep sys.argv check for backward compatibility


def set_debug_mode(debug: bool) -> None:
    """
    Set debug mode for minesweeper module.

    Args:
        debug: Whether debug mode is enabled
    """
    global DEBUG_MODE
    DEBUG_MODE = debug


def _parse_timestamp(timestamp_str: Optional[str]) -> datetime:
    """Parse ISO timestamp strings and normalize to UTC-aware datetimes."""
    if not timestamp_str:
        return datetime.now(timezone.utc)

    try:
        parsed = datetime.fromisoformat(timestamp_str)
    except ValueError:
        logger.warning(
            "Failed to parse timestamp '%s', defaulting to current UTC time",
            timestamp_str,
        )
        return datetime.now(timezone.utc)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def get_minesweeper_icons() -> Tuple[Optional[str], Optional[str]]:
    """
    Load minesweeper game icons (claim point and mine).

    Returns:
        Tuple of (claim_point_icon_b64, mine_icon_b64)
        Either or both can be None if loading fails
    """
    claim_point_icon = None
    mine_icon = None

    # Load claim point icon from slots directory
    try:
        claim_icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "slots", "claim_icon.png"
        )
        with open(claim_icon_path, "rb") as f:
            claim_icon_bytes = f.read()
            claim_point_icon = base64.b64encode(claim_icon_bytes).decode("utf-8")
    except Exception as e:
        logger.warning(f"Failed to load claim icon: {e}")

    # Load mine icon from minesweeper directory
    try:
        mine_icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "minesweeper", "mine_icon.png"
        )
        with open(mine_icon_path, "rb") as f:
            mine_icon_bytes = f.read()
            mine_icon = base64.b64encode(mine_icon_bytes).decode("utf-8")
    except Exception as e:
        logger.warning(f"Failed to load mine icon: {e}")

    return claim_point_icon, mine_icon


def get_source_icon(source_type: str, source_id: int) -> Optional[str]:
    """
    Get the slot icon for a minesweeper game source.

    Args:
        source_type: "user" or "character"
        source_id: user_id for users, character id for characters

    Returns:
        Base64-encoded icon or None if not found
    """
    from utils import database

    normalized_type = (source_type or "").strip().lower()

    if normalized_type == "user":
        user = database.get_user(source_id)
        if user and user.slot_iconb64:
            return user.slot_iconb64
    elif normalized_type == "character":
        character = database.get_character_by_id(source_id)
        if character and character.slot_iconb64:
            return character.slot_iconb64

    logger.warning(f"No icon found for source {source_type}:{source_id}")
    return None


def generate_mine_positions(n: int = 2) -> List[int]:
    """
    Generate random mine positions for a 3x3 grid (indices 0-8).

    Args:
        n: Number of mines to generate (default 2)

    Returns:
        List of n unique random positions where mines are placed.
    """
    if n > GRID_SIZE:
        logger.error(f"Cannot generate {n} mines for grid of size {GRID_SIZE}")
        n = GRID_SIZE
    positions = random.sample(range(GRID_SIZE), n)
    logger.debug(f"Generated {n} mine positions: {positions}")
    return positions


def generate_claim_point_position(mine_positions: List[int], n: int = 1) -> List[int]:
    """
    Generate random claim point positions that don't overlap with mines.

    Args:
        mine_positions: List of cell indices where mines are placed
        n: Number of claim points to generate (default 1)

    Returns:
        List containing n positions where claim points are placed.
    """
    available_positions = [i for i in range(GRID_SIZE) if i not in mine_positions]
    if not available_positions:
        logger.error("No available positions for claim points")
        return []
    if n > len(available_positions):
        logger.warning(
            f"Cannot generate {n} claim points, only {len(available_positions)} positions available"
        )
        n = len(available_positions)
    positions = random.sample(available_positions, n)
    logger.debug(f"Generated {n} claim point positions: {positions}")
    return positions


def _game_model_to_pydantic(game_orm: MinesweeperGameModel) -> MinesweeperGame:
    """Convert SQLAlchemy MinesweeperGameModel to Pydantic MinesweeperGame."""
    return MinesweeperGame.from_orm(game_orm)


def get_existing_game(user_id: int, chat_id: str) -> Optional[MinesweeperGame]:
    """
    Get an existing game if one exists.

    Returns:
    - Active game (always returned, regardless of time)
    - Completed game (won/lost) if it was started less than 24h ago (cooldown period)
    - None if no game exists or completed game cooldown has expired

    Args:
        user_id: Telegram user ID
        chat_id: Chat ID where the game is played

    Returns:
        MinesweeperGame object or None if no game exists or cooldown expired
    """
    with get_session() as session:
        game_orm = (
            session.query(MinesweeperGameModel)
            .filter(
                MinesweeperGameModel.user_id == user_id,
                MinesweeperGameModel.chat_id == chat_id,
            )
            .order_by(MinesweeperGameModel.started_timestamp.desc())
            .first()
        )

        if not game_orm:
            return None

        game = _game_model_to_pydantic(game_orm)

        # If game is still active, always return it (no expiration for active games)
        if game.status == "active":
            logger.info(
                f"Found existing active game {game.id} for user {user_id} in chat {chat_id}"
            )
            return game

        # For completed games (won/lost), check if 24h cooldown has passed
        cooldown_seconds = 60 if DEBUG_MODE else 24 * 60 * 60

        time_since_start = datetime.now(timezone.utc) - game.started_timestamp
        if time_since_start.total_seconds() < cooldown_seconds:
            # Still in cooldown period
            if DEBUG_MODE:
                logger.info(
                    f"Found completed game {game.id} for user {user_id} in chat {chat_id} "
                    f"(started {time_since_start.total_seconds():.0f}s ago, still in cooldown)"
                )
            else:
                logger.info(
                    f"Found completed game {game.id} for user {user_id} in chat {chat_id} "
                    f"(started {time_since_start.total_seconds() / 3600:.1f}h ago, still in cooldown)"
                )
            return game

        # Cooldown has passed, user can create a new game
        logger.info(
            f"Last game {game.id} for user {user_id} in chat {chat_id} is outside cooldown period"
        )
        return None


def create_game(
    user_id: int, chat_id: str, bet_card_id: int, bet_card_title: str, bet_card_rarity: str
) -> Optional[MinesweeperGame]:
    """
    Create a new minesweeper game.

    This function does NOT check for existing games or cooldown periods.
    Caller must validate these conditions before calling.

    Args:
        user_id: Telegram user ID
        chat_id: Chat ID where the game is played
        bet_card_id: Card ID being bet on this game
        bet_card_title: Display title of the bet card (preserved even if card is deleted)
        bet_card_rarity: Rarity of the bet card (preserved even if card is deleted)

    Returns:
        MinesweeperGame object or None on failure
    """
    # Select a random source (user or character) from the chat
    selected_profile = rolling.select_random_source_with_image(chat_id)
    if not selected_profile:
        logger.warning(f"No eligible sources found for minesweeper game in chat {chat_id}")
        return None

    mine_positions = generate_mine_positions(MINESWEEPER_MINE_COUNT)
    claim_point_positions = generate_claim_point_position(
        mine_positions, MINESWEEPER_CLAIM_POINT_COUNT
    )
    now = datetime.now(timezone.utc)

    with get_session(commit=True) as session:
        game_orm = MinesweeperGameModel(
            user_id=user_id,
            chat_id=chat_id,
            bet_card_id=bet_card_id,
            bet_card_title=bet_card_title,
            bet_card_rarity=bet_card_rarity,
            mine_positions=json.dumps(mine_positions),
            claim_point_positions=json.dumps(claim_point_positions),
            revealed_cells=json.dumps([]),
            status="active",
            moves_count=0,
            started_timestamp=now,
            last_updated_timestamp=now,
            source_type=selected_profile.source_type,
            source_id=selected_profile.source_id,
        )
        session.add(game_orm)
        session.flush()

        game = MinesweeperGame(
            id=game_orm.id,
            user_id=user_id,
            chat_id=chat_id,
            bet_card_id=bet_card_id,
            bet_card_title=bet_card_title,
            bet_card_rarity=bet_card_rarity,
            mine_positions=mine_positions,
            claim_point_positions=claim_point_positions,
            revealed_cells=[],
            status="active",
            moves_count=0,
            reward_card_id=None,
            started_timestamp=now,
            last_updated_timestamp=now,
            source_type=selected_profile.source_type,
            source_id=selected_profile.source_id,
        )

        logger.info(
            f"Created new minesweeper game {game_orm.id} for user {user_id} in chat {chat_id}"
        )
        return game


def get_game_by_id(game_id: int) -> Optional[MinesweeperGame]:
    """
    Get a minesweeper game by ID.

    Args:
        game_id: Game ID

    Returns:
        MinesweeperGame object or None if not found
    """
    with get_session() as session:
        game_orm = (
            session.query(MinesweeperGameModel).filter(MinesweeperGameModel.id == game_id).first()
        )

        if not game_orm:
            return None

        return _game_model_to_pydantic(game_orm)


def reveal_cell(game_id: int, cell_index: int) -> Optional[MinesweeperGame]:
    """
    Reveal a cell in the minesweeper game and update game state.

    Args:
        game_id: Game ID
        cell_index: Cell index to reveal (0-8)

    Returns:
        Updated MinesweeperGame object or None on failure
    """
    # Get the current game state
    game = get_game_by_id(game_id)
    if not game:
        logger.warning(f"Cannot reveal cell: game {game_id} not found")
        return None

    # Validate game state
    if game.status != "active":
        logger.warning(f"Cannot reveal cell: game {game_id} is not active (status: {game.status})")
        return game

    # Validate cell index
    if cell_index < 0 or cell_index >= GRID_SIZE:
        logger.warning(f"Cannot reveal cell: invalid cell_index {cell_index}")
        return None

    # Check if cell was already revealed
    if cell_index in game.revealed_cells:
        logger.warning(f"Cannot reveal cell: cell {cell_index} already revealed in game {game_id}")
        return game

    # Add cell to revealed cells
    new_revealed_cells = game.revealed_cells + [cell_index]
    new_moves_count = game.moves_count + 1
    new_status = game.status

    # Check if the cell has a mine
    is_mine = cell_index in game.mine_positions

    if is_mine:
        # Player hit a mine - game lost
        new_status = "lost"
        logger.info(f"Game {game_id}: Player revealed mine at cell {cell_index} - LOST")
    else:
        # Count only character/card icon cells (exclude both mines and claim points)
        character_cells_revealed = len(
            [
                cell
                for cell in new_revealed_cells
                if cell not in game.mine_positions and cell not in game.claim_point_positions
            ]
        )

        if character_cells_revealed >= SAFE_REVEALS_REQUIRED:
            # Player revealed enough character cells - game won
            new_status = "won"
            logger.info(
                f"Game {game_id}: Player revealed {character_cells_revealed} character cells - WON"
            )
        else:
            logger.info(
                f"Game {game_id}: Cell {cell_index} revealed. Character cells: {character_cells_revealed}/{SAFE_REVEALS_REQUIRED}"
            )

    # Update the database
    now = datetime.now(timezone.utc)
    with get_session(commit=True) as session:
        game_orm = (
            session.query(MinesweeperGameModel).filter(MinesweeperGameModel.id == game_id).first()
        )

        if game_orm:
            game_orm.revealed_cells = json.dumps(new_revealed_cells)
            game_orm.moves_count = new_moves_count
            game_orm.status = new_status
            game_orm.last_updated_timestamp = now

    # Return updated game state
    return MinesweeperGame(
        id=game.id,
        user_id=game.user_id,
        chat_id=game.chat_id,
        bet_card_id=game.bet_card_id,
        bet_card_title=game.bet_card_title,
        bet_card_rarity=game.bet_card_rarity,
        mine_positions=game.mine_positions,
        claim_point_positions=game.claim_point_positions,
        revealed_cells=new_revealed_cells,
        status=new_status,
        moves_count=new_moves_count,
        reward_card_id=game.reward_card_id,
        started_timestamp=game.started_timestamp,
        last_updated_timestamp=now,
        source_type=game.source_type,
        source_id=game.source_id,
    )
