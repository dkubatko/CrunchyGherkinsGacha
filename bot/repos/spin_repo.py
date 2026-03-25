"""Spin repository for database access to user spin balances.

This module provides data access functions for retrieving, consuming,
and modifying spin balances, as well as megaspin tracking.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from settings.constants import SPINS_FOR_MEGASPIN
from utils.models import MegaspinsModel, SpinsModel
from utils.schemas import Megaspins, Spins
from utils.session import with_session

logger = logging.getLogger(__name__)


def _get_spins_for_megaspin() -> int:
    """Get SPINS_FOR_MEGASPIN from config. Returns the number of spins required for a megaspin.
    In DEBUG_MODE, returns 5 for easier testing.
    """
    from api.config import DEBUG_MODE

    if DEBUG_MODE:
        return 5
    return SPINS_FOR_MEGASPIN


@with_session
def get_user_spins(user_id: int, chat_id: str, *, session: Session) -> Optional[Spins]:
    """Get the spins record for a user in a specific chat."""
    result = (
        session.query(SpinsModel)
        .filter(
            SpinsModel.user_id == user_id,
            SpinsModel.chat_id == str(chat_id),
        )
        .first()
    )
    return Spins.from_orm(result) if result else None


@with_session
def get_user_spin_count(user_id: int, chat_id: str, *, session: Session) -> int:
    """Get the current spin count for a user in a specific chat. Returns 0 if no record exists."""
    spins = (
        session.query(SpinsModel)
        .filter(
            SpinsModel.user_id == user_id,
            SpinsModel.chat_id == str(chat_id),
        )
        .first()
    )
    return spins.count if spins else 0


@with_session(commit=True)
def increment_user_spins(user_id: int, chat_id: str, amount: int = 1, *, session: Session) -> Optional[int]:
    """Increment the spin count for a user in a specific chat. Returns new count or None if user not found."""
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
    spins = SpinsModel(
        user_id=user_id,
        chat_id=str(chat_id),
        count=amount,
        login_streak=0,
        last_bonus_date=None,
    )
    session.add(spins)
    return amount


@with_session(commit=True)
def decrement_user_spins(user_id: int, chat_id: str, amount: int = 1, *, session: Session) -> Optional[int]:
    """Decrement the spin count for a user in a specific chat. Returns new count or None if insufficient spins."""
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


@with_session(commit=True)
def consume_user_spin(user_id: int, chat_id: str, *, session: Session) -> bool:
    """Consume one spin if available. Returns True if successful, False if no spins available."""
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


@with_session(commit=True)
def get_user_megaspins(user_id: int, chat_id: str, *, session: Session) -> Megaspins:
    """Get or create the megaspin record for a user in a specific chat."""
    spins_for_megaspin = _get_spins_for_megaspin()

    megaspins = (
        session.query(MegaspinsModel)
        .filter(
            MegaspinsModel.user_id == user_id,
            MegaspinsModel.chat_id == str(chat_id),
        )
        .first()
    )

    if not megaspins:
        # Create default megaspins record
        megaspins = MegaspinsModel(
            user_id=user_id,
            chat_id=str(chat_id),
            spins_until_megaspin=spins_for_megaspin,
            megaspin_available=False,
        )
        session.add(megaspins)

    session.flush()
    return Megaspins.from_orm(megaspins)


@with_session(commit=True)
def consume_megaspin(user_id: int, chat_id: str, *, session: Session) -> bool:
    """Consume a megaspin if available. Returns True if successful, False otherwise."""
    spins_for_megaspin = _get_spins_for_megaspin()

    megaspins = (
        session.query(MegaspinsModel)
        .filter(
            MegaspinsModel.user_id == user_id,
            MegaspinsModel.chat_id == str(chat_id),
        )
        .first()
    )

    if not megaspins or not megaspins.megaspin_available:
        return False

    # Consume the megaspin and reset the counter
    megaspins.megaspin_available = False
    megaspins.spins_until_megaspin = spins_for_megaspin
    logger.info(f"User {user_id} in chat {chat_id} consumed their megaspin")
    return True


@with_session(commit=True)
def reset_megaspin_counter(user_id: int, chat_id: str, *, session: Session) -> Megaspins:
    """Reset the megaspin counter to SPINS_FOR_MEGASPIN and set megaspin_available=False.

    This is typically called after consuming a megaspin.
    """
    spins_for_megaspin = _get_spins_for_megaspin()

    megaspins = (
        session.query(MegaspinsModel)
        .filter(
            MegaspinsModel.user_id == user_id,
            MegaspinsModel.chat_id == str(chat_id),
        )
        .first()
    )

    if not megaspins:
        megaspins = MegaspinsModel(
            user_id=user_id,
            chat_id=str(chat_id),
            spins_until_megaspin=spins_for_megaspin,
            megaspin_available=False,
        )
        session.add(megaspins)
    else:
        megaspins.megaspin_available = False
        megaspins.spins_until_megaspin = spins_for_megaspin

    session.flush()
    return Megaspins.from_orm(megaspins)


@with_session(commit=True)
def create_user_spins(
    user_id: int,
    chat_id: str,
    count: int,
    login_streak: int,
    last_bonus_date,
    *,
    session: Session,
) -> Spins:
    """Create a new SpinsModel record."""
    spins = SpinsModel(
        user_id=user_id,
        chat_id=str(chat_id),
        count=count,
        login_streak=login_streak,
        last_bonus_date=last_bonus_date,
    )
    session.add(spins)
    session.flush()
    return Spins.from_orm(spins)


@with_session(commit=True)
def create_user_megaspins(
    user_id: int,
    chat_id: str,
    spins_until_megaspin: int,
    megaspin_available: bool,
    *,
    session: Session,
) -> Megaspins:
    """Create a new MegaspinsModel record."""
    megaspins = MegaspinsModel(
        user_id=user_id,
        chat_id=str(chat_id),
        spins_until_megaspin=spins_until_megaspin,
        megaspin_available=megaspin_available,
    )
    session.add(megaspins)
    session.flush()
    return Megaspins.from_orm(megaspins)


@with_session(commit=True)
def update_user_spins(
    user_id: int,
    chat_id: str,
    *,
    count: int,
    login_streak: int,
    last_bonus_date,
    session: Session,
) -> None:
    """Update spin count, login streak, and last bonus date for a user."""
    spins = session.query(SpinsModel).filter_by(user_id=user_id, chat_id=str(chat_id)).first()
    if spins:
        spins.count = count
        spins.login_streak = login_streak
        spins.last_bonus_date = last_bonus_date


@with_session(commit=True)
def update_user_megaspins(
    user_id: int,
    chat_id: str,
    *,
    spins_until_megaspin: int,
    megaspin_available: bool,
    session: Session,
) -> None:
    """Update megaspin counter and availability for a user."""
    ms = session.query(MegaspinsModel).filter_by(user_id=user_id, chat_id=str(chat_id)).first()
    if ms:
        ms.spins_until_megaspin = spins_until_megaspin
        ms.megaspin_available = megaspin_available
