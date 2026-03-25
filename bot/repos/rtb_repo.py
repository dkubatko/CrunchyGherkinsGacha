"""Ride the Bus (RTB) repository for database access to game state.

This module provides data access functions for retrieving RTB game records.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from utils.models import RideTheBusGameModel
from utils.schemas import RideTheBusGame
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session
def get_active_game(user_id: int, chat_id: str, *, session: Session) -> Optional[RideTheBusGame]:
    """Get an active RTB game for a user in a chat.

    DEPRECATED: Use get_existing_game instead to properly handle cooldowns.
    This function only returns active games, not games in cooldown.
    """
    result = (
        session.query(RideTheBusGameModel)
        .filter(
            RideTheBusGameModel.user_id == user_id,
            RideTheBusGameModel.chat_id == chat_id,
            RideTheBusGameModel.status == "active",
        )
        .order_by(RideTheBusGameModel.started_timestamp.desc())
        .first()
    )
    return RideTheBusGame.from_orm(result) if result else None


@with_session
def get_game_by_id(game_id: int, *, session: Session) -> Optional[RideTheBusGame]:
    """Get an RTB game by ID."""
    result = (
        session.query(RideTheBusGameModel).filter(RideTheBusGameModel.id == game_id).first()
    )
    return RideTheBusGame.from_orm(result) if result else None


@with_session
def get_latest_game(user_id: int, chat_id: str, *, session: Session) -> Optional[RideTheBusGame]:
    """Get the most recent RTB game for a user in a chat (any status)."""
    result = (
        session.query(RideTheBusGameModel)
        .filter(
            RideTheBusGameModel.user_id == user_id,
            RideTheBusGameModel.chat_id == chat_id,
        )
        .order_by(RideTheBusGameModel.started_timestamp.desc())
        .first()
    )
    return RideTheBusGame.from_orm(result) if result else None


@with_session
def get_game_for_update(game_id: int, *, session: Session) -> Optional[RideTheBusGame]:
    """Get an RTB game by ID with row lock."""
    result = (
        session.query(RideTheBusGameModel)
        .filter(RideTheBusGameModel.id == game_id)
        .with_for_update()
        .first()
    )
    return RideTheBusGame.from_orm(result) if result else None


@with_session(commit=True)
def create_game(*, session: Session, **kwargs) -> RideTheBusGame:
    """Create a new RTB game record and flush to obtain its ID."""
    game = RideTheBusGameModel(**kwargs)
    session.add(game)
    session.flush()
    return RideTheBusGame.from_orm(game)


@with_session(commit=True)
def update_game_state(
    game_id: int,
    *,
    current_position: Optional[int] = None,
    current_multiplier: Optional[int] = None,
    status: Optional[str] = None,
    last_updated_timestamp=None,
    session: Session,
) -> bool:
    """Update game state fields."""
    game = session.query(RideTheBusGameModel).filter(RideTheBusGameModel.id == game_id).first()
    if not game:
        return False
    if current_position is not None:
        game.current_position = current_position
    if current_multiplier is not None:
        game.current_multiplier = current_multiplier
    if status is not None:
        game.status = status
    if last_updated_timestamp is not None:
        game.last_updated_timestamp = last_updated_timestamp
    return True
