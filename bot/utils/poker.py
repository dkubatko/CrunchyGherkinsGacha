"""
Poker game logic and database interactions.

This module handles:
- Game state management
- Player joining/leaving
- WebSocket connections and broadcasting
- Database operations for poker games and players
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import WebSocket
from pydantic import BaseModel

logger = logging.getLogger(__name__)


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
        cls, player: "PokerPlayer", slot_iconb64: Optional[str] = None
    ) -> "PokerPlayerInfo":
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
    current_player_turn: Optional[int] = None
    dealer_position: Optional[int] = None
    players: List[PokerPlayerInfo]

    @classmethod
    def from_db_models(
        cls,
        game: "PokerGame",
        players: List["PokerPlayer"],
        slot_icons: Optional[Dict[int, str]] = None,
    ) -> "PokerGameStateResponse":
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


class ConnectionManager:
    """Manages WebSocket connections for poker games."""

    def __init__(self):
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, chat_id: str, user_id: int):
        """
        Store a WebSocket connection (assumes websocket is already accepted).

        Args:
            websocket: The WebSocket connection (already accepted)
            chat_id: The chat/game identifier
            user_id: The user's ID
        """
        connection_id = f"{user_id}_{id(websocket)}"

        if chat_id not in self.active_connections:
            self.active_connections[chat_id] = {}

        self.active_connections[chat_id][connection_id] = websocket
        logger.info(
            f"WebSocket connected: user_id={user_id}, chat_id={chat_id}, connection_id={connection_id}"
        )

    def disconnect(self, chat_id: str, user_id: int, websocket: WebSocket):
        """
        Remove a WebSocket connection.

        Args:
            chat_id: The chat/game identifier
            user_id: The user's ID
            websocket: The WebSocket connection to remove
        """
        connection_id = f"{user_id}_{id(websocket)}"

        if chat_id in self.active_connections:
            if connection_id in self.active_connections[chat_id]:
                del self.active_connections[chat_id][connection_id]
                logger.info(f"WebSocket disconnected: user_id={user_id}, chat_id={chat_id}")

            # Clean up empty chat rooms
            if not self.active_connections[chat_id]:
                del self.active_connections[chat_id]

    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        """
        Send a typed message to a specific WebSocket connection.

        Args:
            message: The message dictionary (from a Pydantic model's .dict() method)
            websocket: The target WebSocket connection
        """
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")

    async def broadcast_to_chat(self, message: Dict[str, Any], chat_id: str):
        """
        Broadcast a typed message to all connections in a chat.

        Args:
            message: The message dictionary (from a Pydantic model's .dict() method)
            chat_id: The chat/game identifier
        """
        if chat_id not in self.active_connections:
            return

        disconnected = []
        for connection_id, websocket in self.active_connections[chat_id].items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to {connection_id}: {e}")
                disconnected.append(connection_id)

        # Clean up disconnected sockets
        for connection_id in disconnected:
            del self.active_connections[chat_id][connection_id]


# Global connection manager
manager = ConnectionManager()


def get_game_state(
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
    return get_game_state(chat_id)


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
