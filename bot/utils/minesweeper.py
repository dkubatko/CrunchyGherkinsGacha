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
import random
import sys
import os
from datetime import datetime
from typing import Optional, List, Tuple

from utils.database import MinesweeperGame, connect
from utils import rolling
from settings.constants import MINESWEEPER_MINE_COUNT, MINESWEEPER_CLAIM_POINT_COUNT

logger = logging.getLogger(__name__)

# Constants
GRID_SIZE = 9  # 3x3 grid
SAFE_REVEALS_REQUIRED = 3  # Number of safe cells to reveal to win
DEBUG_MODE = "--debug" in sys.argv or os.getenv("DEBUG", "").lower() in ("true", "1", "yes")


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
    conn = connect()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id, user_id, chat_id, bet_card_id, bet_card_title, bet_card_rarity, mine_positions, claim_point_positions, revealed_cells,
                   status, moves_count, reward_card_id, started_timestamp, last_updated_timestamp,
                   source_type, source_id
            FROM minesweeper_games
            WHERE user_id = ? AND chat_id = ?
            ORDER BY started_timestamp DESC
            LIMIT 1
            """,
            (user_id, chat_id),
        )

        row = cursor.fetchone()

        if not row:
            return None

        game = MinesweeperGame(
            id=row[0],
            user_id=row[1],
            chat_id=row[2],
            bet_card_id=row[3],
            bet_card_title=row[4],
            bet_card_rarity=row[5],
            mine_positions=json.loads(row[6]),
            claim_point_positions=json.loads(row[7]),
            revealed_cells=json.loads(row[8]),
            status=row[9],
            moves_count=row[10],
            reward_card_id=row[11],
            started_timestamp=datetime.fromisoformat(row[12]),
            last_updated_timestamp=datetime.fromisoformat(row[13]),
            source_type=row[14],
            source_id=row[15],
        )

        # If game is still active, always return it (no expiration for active games)
        if game.status == "active":
            logger.info(
                f"Found existing active game {game.id} for user {user_id} in chat {chat_id}"
            )
            return game

        # For completed games (won/lost), check if 24h cooldown has passed
        cooldown_seconds = 60 if DEBUG_MODE else 24 * 60 * 60

        time_since_start = datetime.now() - game.started_timestamp
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

    except Exception as e:
        logger.error(f"Error getting existing minesweeper game: {e}")
        return None
    finally:
        conn.close()


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
    conn = connect()
    cursor = conn.cursor()

    try:
        # Select a random source (user or character) from the chat
        selected_profile = rolling.select_random_source_with_image(chat_id)
        if not selected_profile:
            logger.warning(f"No eligible sources found for minesweeper game in chat {chat_id}")
            return None

        mine_positions = generate_mine_positions(MINESWEEPER_MINE_COUNT)
        claim_point_positions = generate_claim_point_position(
            mine_positions, MINESWEEPER_CLAIM_POINT_COUNT
        )
        now = datetime.now()

        cursor.execute(
            """
            INSERT INTO minesweeper_games
            (user_id, chat_id, bet_card_id, bet_card_title, bet_card_rarity, mine_positions, claim_point_positions, revealed_cells, status, moves_count, started_timestamp, last_updated_timestamp, source_type, source_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', 0, ?, ?, ?, ?)
            """,
            (
                user_id,
                chat_id,
                bet_card_id,
                bet_card_title,
                bet_card_rarity,
                json.dumps(mine_positions),
                json.dumps(claim_point_positions),
                json.dumps([]),
                now.isoformat(),
                now.isoformat(),
                selected_profile.source_type,
                selected_profile.source_id,
            ),
        )

        game_id = cursor.lastrowid
        conn.commit()

        game = MinesweeperGame(
            id=game_id,
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

        logger.info(f"Created new minesweeper game {game_id} for user {user_id} in chat {chat_id}")
        return game

    except Exception as e:
        logger.error(f"Error creating minesweeper game: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()


def get_game_by_id(game_id: int) -> Optional[MinesweeperGame]:
    """
    Get a minesweeper game by ID.

    Args:
        game_id: Game ID

    Returns:
        MinesweeperGame object or None if not found
    """
    conn = connect()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id, user_id, chat_id, bet_card_id, bet_card_title, bet_card_rarity, mine_positions, claim_point_positions, revealed_cells,
                   status, moves_count, reward_card_id, started_timestamp, last_updated_timestamp,
                   source_type, source_id
            FROM minesweeper_games
            WHERE id = ?
            """,
            (game_id,),
        )

        row = cursor.fetchone()

        if not row:
            return None

        return MinesweeperGame(
            id=row[0],
            user_id=row[1],
            chat_id=row[2],
            bet_card_id=row[3],
            bet_card_title=row[4],
            bet_card_rarity=row[5],
            mine_positions=json.loads(row[6]),
            claim_point_positions=json.loads(row[7]),
            revealed_cells=json.loads(row[8]),
            status=row[9],
            moves_count=row[10],
            reward_card_id=row[11],
            started_timestamp=datetime.fromisoformat(row[12]),
            last_updated_timestamp=datetime.fromisoformat(row[13]),
            source_type=row[14],
            source_id=row[15],
        )

    except Exception as e:
        logger.error(f"Error getting minesweeper game {game_id}: {e}")
        return None
    finally:
        conn.close()


def reveal_cell(game_id: int, cell_index: int) -> Optional[MinesweeperGame]:
    """
    Reveal a cell in the minesweeper game and update game state.

    Args:
        game_id: Game ID
        cell_index: Cell index to reveal (0-8)

    Returns:
        Updated MinesweeperGame object or None on failure
    """
    conn = connect()
    cursor = conn.cursor()

    try:
        # Get the current game state
        game = get_game_by_id(game_id)
        if not game:
            logger.warning(f"Cannot reveal cell: game {game_id} not found")
            return None

        # Validate game state
        if game.status != "active":
            logger.warning(
                f"Cannot reveal cell: game {game_id} is not active (status: {game.status})"
            )
            return game

        # Validate cell index
        if cell_index < 0 or cell_index >= GRID_SIZE:
            logger.warning(f"Cannot reveal cell: invalid cell_index {cell_index}")
            return None

        # Check if cell was already revealed
        if cell_index in game.revealed_cells:
            logger.warning(
                f"Cannot reveal cell: cell {cell_index} already revealed in game {game_id}"
            )
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
        now = datetime.now()
        cursor.execute(
            """
            UPDATE minesweeper_games
            SET revealed_cells = ?,
                moves_count = ?,
                status = ?,
                last_updated_timestamp = ?
            WHERE id = ?
            """,
            (
                json.dumps(new_revealed_cells),
                new_moves_count,
                new_status,
                now.isoformat(),
                game_id,
            ),
        )

        conn.commit()

        # Return updated game state
        return MinesweeperGame(
            id=game.id,
            user_id=game.user_id,
            chat_id=game.chat_id,
            bet_card_id=game.bet_card_id,
            mine_positions=game.mine_positions,
            claim_point_positions=game.claim_point_positions,
            revealed_cells=new_revealed_cells,
            status=new_status,
            moves_count=new_moves_count,
            reward_card_id=game.reward_card_id,
            started_timestamp=game.started_timestamp,
            last_updated_timestamp=now,
        )

    except Exception as e:
        logger.error(f"Error revealing cell in game {game_id}: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()
