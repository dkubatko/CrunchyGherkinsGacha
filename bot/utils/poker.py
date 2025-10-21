"""
Poker game logic and database interactions.

This module handles:
- Game state management
- Player joining/leaving
- Socket.IO interactions and broadcasting
- Database operations for poker games and players
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from pydantic import BaseModel
from socketio import AsyncServer

from settings.constants import POKER_NAMESPACE
from utils.database import PokerGame, PokerPlayer

logger = logging.getLogger(__name__)

# Game timing constants
DEBUG_MODE = "--debug" in os.sys.argv or os.getenv("DEBUG_MODE") == "1"
COUNTDOWN_DURATION_SECONDS = 5 if DEBUG_MODE else 60

# Track countdown tasks per chat_id
_countdown_tasks: Dict[str, asyncio.Task] = {}

# Socket server reference and session tracking (sid -> {chat_id, user_id})
_socket_server: Optional[AsyncServer] = None
_sessions: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# Response Models
# ============================================================================


class PokerPlayerInfo(BaseModel):
    """Player information in game state."""

    user_id: int
    seat_position: int
    betting_balance: int
    current_bet: int
    total_bet: int
    status: str
    last_action: Optional[str] = None
    slot_iconb64: Optional[str] = None

    @classmethod
    def from_db_model(
        cls, player: PokerPlayer, slot_iconb64: Optional[str] = None
    ) -> PokerPlayerInfo:
        """Create PokerPlayerInfo from database PokerPlayer model."""
        return cls(
            user_id=player.user_id,
            seat_position=player.seat_position,
            betting_balance=player.betting_balance,
            current_bet=player.current_bet,
            total_bet=player.total_bet,
            status=player.status,
            last_action=player.last_action,
            slot_iconb64=slot_iconb64,
        )


class PokerGameStateResponse(BaseModel):
    """Complete poker game state response."""

    game_id: Optional[int] = None
    chat_id: str
    status: str
    pot: int
    current_bet: int
    min_betting_balance: Optional[int] = None
    community_cards: List[Dict[str, Any]]
    countdown_start_time: Optional[str] = None
    countdown_duration_seconds: int = COUNTDOWN_DURATION_SECONDS
    current_player_turn: Optional[int] = None
    dealer_position: Optional[int] = None
    players: List[PokerPlayerInfo]

    @classmethod
    def from_db_models(
        cls,
        game: PokerGame,
        players: List[PokerPlayer],
        slot_icons: Optional[Dict[int, str]] = None,
    ) -> PokerGameStateResponse:
        """Create PokerGameStateResponse from database models.

        Args:
            game: The poker game model
            players: List of poker player models
            slot_icons: Optional dict mapping user_id to slot_iconb64
        """
        slot_icons = slot_icons or {}
        return cls(
            game_id=game.id,
            chat_id=game.chat_id,
            status=game.status,
            pot=game.pot,
            current_bet=game.current_bet,
            min_betting_balance=game.min_betting_balance,
            community_cards=game.community_cards,
            countdown_start_time=(
                game.countdown_start_time.isoformat() if game.countdown_start_time else None
            ),
            current_player_turn=game.current_player_turn,
            dealer_position=game.dealer_position,
            players=[PokerPlayerInfo.from_db_model(p, slot_icons.get(p.user_id)) for p in players],
        )


# ============================================================================
# Internal Helpers (Private)
# ============================================================================


async def _emit_game_state(
    chat_id: str,
    game_state: Optional[PokerGameStateResponse],
    *,
    target_sid: Optional[str] = None,
    event: str = "game_state",
) -> None:
    """Emit a serialized game state to a room or specific socket."""

    if not _socket_server:
        logger.warning("Socket server not configured; cannot emit %s", event)
        return

    payload = game_state.dict() if game_state else None
    target = target_sid if target_sid else chat_id
    await _socket_server.emit(event, payload, to=target, namespace=POKER_NAMESPACE)


def _get_game_state(
    chat_id: str, include_slot_icons: bool = False
) -> Optional[PokerGameStateResponse]:
    """
    Get the current game state for a chat.

    Args:
        chat_id: The chat identifier
        include_slot_icons: Whether to include slot icons (only needed on initial load and player join)

    Returns:
        Typed game state response or None if no active game
    """
    from utils.database import get_active_poker_game, get_poker_players, get_poker_player_slot_icons

    game = get_active_poker_game(chat_id)
    if not game:
        return None

    players = get_poker_players(game.id)
    slot_icons = get_poker_player_slot_icons(game.id) if include_slot_icons else None
    return PokerGameStateResponse.from_db_models(game, players, slot_icons)


async def _start_game_after_countdown(chat_id: str):
    """
    Internal function that waits for countdown duration then starts the game.

    Args:
        chat_id: The chat identifier
    """
    try:
        # Wait for countdown duration
        await asyncio.sleep(COUNTDOWN_DURATION_SECONDS)

        from utils.database import (
            get_active_poker_game,
            get_poker_players,
            update_poker_game_status,
        )

        game = get_active_poker_game(chat_id)
        if not game or game.status != "countdown":
            logger.info(f"Game no longer in countdown status: chat_id={chat_id}")
            return

        # Check player count
        players = get_poker_players(game.id)
        active_players = [p for p in players if p.status != "out"]

        if len(active_players) >= 2:
            # Start the game
            update_poker_game_status(game.id, "playing")
            logger.info(f"Game started after countdown: game_id={game.id}, chat_id={chat_id}")

            # Broadcast game state to all players
            game_state = _get_game_state(chat_id, include_slot_icons=False)
            await broadcast_game_state(chat_id, game_state)
        else:
            # Not enough players, revert to waiting
            update_poker_game_status(game.id, "waiting")
            logger.info(f"Game reverted to waiting (not enough players): game_id={game.id}")

            # Broadcast updated state
            game_state = _get_game_state(chat_id, include_slot_icons=False)
            await broadcast_game_state(chat_id, game_state)

    except asyncio.CancelledError:
        logger.info(f"Countdown task cancelled: chat_id={chat_id}")
        raise
    except Exception as e:
        logger.error(f"Error in countdown task for chat_id={chat_id}: {e}")
    finally:
        # Remove task from tracker
        if chat_id in _countdown_tasks:
            del _countdown_tasks[chat_id]


def _schedule_game_start(chat_id: str):
    """
    Schedule a game to start after the countdown duration.
    Cancels any existing countdown for this chat.

    Args:
        chat_id: The chat identifier
    """
    # Cancel existing countdown task if any
    cancel_countdown(chat_id)

    # Schedule new countdown task
    task = asyncio.create_task(_start_game_after_countdown(chat_id))
    _countdown_tasks[chat_id] = task
    logger.info(
        f"Scheduled game start countdown: chat_id={chat_id}, duration={COUNTDOWN_DURATION_SECONDS}s"
    )


# ============================================================================
# Public API
# ============================================================================


def configure_socket_server(server: AsyncServer) -> None:
    """Configure the Socket.IO server used for poker broadcasting."""

    global _socket_server
    _socket_server = server


def register_session(sid: str, chat_id: str, user_id: int) -> None:
    """Track an active Socket.IO session."""

    _sessions[sid] = {"chat_id": chat_id, "user_id": user_id}


def get_session(sid: str) -> Optional[Dict[str, Any]]:
    """Return session info for a Socket.IO connection."""

    return _sessions.get(sid)


def pop_session(sid: str) -> Optional[Dict[str, Any]]:
    """Remove and return session info for a disconnected Socket.IO client."""

    return _sessions.pop(sid, None)


async def broadcast_game_state(
    chat_id: str,
    game_state: Optional[PokerGameStateResponse],
    *,
    event: str = "game_state",
) -> None:
    """Broadcast the given game state to all players in a chat."""

    await _emit_game_state(chat_id, game_state, event=event)


async def send_initial_state(sid: str, chat_id: str) -> None:
    """Send the initial game state (with slot icons) to a newly connected player."""

    game_state = _get_game_state(chat_id, include_slot_icons=True)
    await _emit_game_state(chat_id, game_state, target_sid=sid)


async def emit_error(sid: str, message: str) -> None:
    """Emit an error payload to a specific socket."""

    if not _socket_server:
        logger.warning("Socket server not configured; cannot emit poker_error")
        return

    await _socket_server.emit(
        "poker_error", {"message": message}, to=sid, namespace=POKER_NAMESPACE
    )


def create_game(chat_id: str) -> PokerGameStateResponse:
    """
    Create a new poker game.

    Args:
        chat_id: The chat identifier

    Returns:
        The created game state
    """
    from utils.database import create_poker_game

    game_id = create_poker_game(chat_id)
    logger.info(f"Created new poker game: game_id={game_id}, chat_id={chat_id}")

    # Fetch the newly created game and return its state
    return _get_game_state(chat_id)


def cancel_countdown(chat_id: str):
    """
    Cancel the countdown task for a chat if it exists.

    Args:
        chat_id: The chat identifier
    """
    if chat_id in _countdown_tasks:
        task = _countdown_tasks[chat_id]
        if not task.done():
            task.cancel()
        del _countdown_tasks[chat_id]
        logger.info(f"Cancelled countdown: chat_id={chat_id}")


async def handle_player_join(
    chat_id: str, user_id: int, spin_balance: int
) -> PokerGameStateResponse:
    """
    Handle a player joining the poker table.

    Args:
        chat_id: The chat identifier
        user_id: The user's ID
        spin_balance: The user's current spin balance

    Returns:
        Updated game state with newly joined player's slot icon included

    Raises:
        ValueError: If player cannot join (insufficient balance, already in game, etc.)
    """
    from utils.database import (
        get_active_poker_game,
        add_poker_player,
        get_poker_players,
        update_poker_game_status,
        get_user,
    )

    # Check minimum balance requirement
    MIN_BALANCE = 10
    if spin_balance < MIN_BALANCE:
        raise ValueError(f"Insufficient balance. Minimum {MIN_BALANCE} spins required.")

    # Get or create game
    game = get_active_poker_game(chat_id)
    if not game:
        from utils.database import create_poker_game as db_create_poker_game

        game_id = db_create_poker_game(chat_id)
        game = get_active_poker_game(chat_id)
    else:
        game_id = game.id

    # Check if player already in game
    players = get_poker_players(game_id)
    if any(p.user_id == user_id and p.status != "out" for p in players):
        raise ValueError("Player already in game")

    # Add player to game
    seat_position = len([p for p in players if p.status != "out"])
    add_poker_player(
        game_id=game_id,
        user_id=user_id,
        chat_id=chat_id,
        seat_position=seat_position,
        spin_balance=spin_balance,
    )

    logger.info(
        f"Player joined: user_id={user_id}, game_id={game_id}, seat_position={seat_position}"
    )

    # Check if we should start countdown
    active_players = [p for p in players if p.status != "out"]
    if len(active_players) + 1 >= 2 and game.status == "waiting":
        # Start countdown
        update_poker_game_status(game_id, "countdown", countdown_start=datetime.now(timezone.utc))
        logger.info(f"Started countdown: game_id={game_id}")

        # Schedule game start after countdown duration
        _schedule_game_start(chat_id)

    # Get updated game state and include only the new player's slot icon
    game = get_active_poker_game(chat_id)
    if not game:
        raise ValueError("Game not found after player join")

    players = get_poker_players(game.id)

    # Fetch only the newly joined player's slot icon
    new_player_slot_icon = {}
    user = get_user(user_id)
    if user and user.slot_iconb64:
        new_player_slot_icon[user_id] = user.slot_iconb64

    return PokerGameStateResponse.from_db_models(game, players, new_player_slot_icon)


async def handle_player_leave(chat_id: str, user_id: int) -> Optional[PokerGameStateResponse]:
    """
    Handle a player leaving the poker table (disconnect) before the game starts.

    Note: Only handles pre-game disconnects (waiting/countdown status).
    In-game disconnects are out of scope for now.

    Args:
        chat_id: The chat identifier
        user_id: The user's ID

    Returns:
        Updated game state, or None if no action was needed
    """
    from utils.database import (
        get_active_poker_game,
        get_poker_players,
        delete_poker_player,
        update_poker_game_status,
    )

    game = get_active_poker_game(chat_id)
    if not game:
        logger.info(f"No active game for player leave: user_id={user_id}, chat_id={chat_id}")
        return None

    # Only handle pre-game disconnects
    if game.status not in ("waiting", "countdown"):
        logger.info(
            f"Player disconnect during game ignored (out of scope): user_id={user_id}, status={game.status}"
        )
        return None

    players = get_poker_players(game.id)

    # Find the player
    player = next((p for p in players if p.user_id == user_id), None)
    if not player:
        logger.info(f"Player not in game: user_id={user_id}")
        return None

    # Remove the player from the database
    delete_poker_player(player.id)
    logger.info(f"Player removed from game (pre-game): user_id={user_id}, game_id={game.id}")

    # Count remaining players (excluding the one we just deleted)
    remaining_players = [p for p in players if p.user_id != user_id and p.status != "out"]

    # If in countdown and less than 2 players remain, cancel countdown and revert to waiting
    if game.status == "countdown" and len(remaining_players) < 2:
        cancel_countdown(chat_id)
        update_poker_game_status(game.id, "waiting")
        logger.info(f"Cancelled countdown due to player leave: game_id={game.id}")

    # Return updated game state
    return _get_game_state(chat_id, include_slot_icons=False)
