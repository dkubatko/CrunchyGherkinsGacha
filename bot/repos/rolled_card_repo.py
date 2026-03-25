"""Rolled card repository for tracking rolled card states.

This module provides all rolled card data access operations including
creating, updating, and checking expiry of rolled cards.
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from utils.models import RolledCardModel
from utils.schemas import RolledCard
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session(commit=True)
def create_rolled_card(card_id: int, original_roller_id: int, *, session: Session) -> int:
    """Create a rolled card entry to track its state."""
    now = datetime.datetime.now(datetime.timezone.utc)
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


@with_session
def get_rolled_card_by_roll_id(roll_id: int, *, session: Session) -> Optional[RolledCard]:
    """Get a rolled card entry by its roll ID."""
    rolled = session.query(RolledCardModel).filter(RolledCardModel.roll_id == roll_id).first()
    return RolledCard.from_orm(rolled) if rolled else None


@with_session
def get_rolled_card_by_card_id(card_id: int, *, session: Session) -> Optional[RolledCard]:
    """Get a rolled card entry by either original or rerolled card ID."""
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
    return RolledCard.from_orm(rolled) if rolled else None


@with_session
def get_rolled_card(roll_id: int, *, session: Session) -> Optional[RolledCard]:
    """Backward-compatible alias for fetching by roll ID."""
    return get_rolled_card_by_roll_id(roll_id, session=session)


@with_session(commit=True)
def update_rolled_card_attempted_by(roll_id: int, username: str, *, session: Session) -> None:
    """Add a username to the attempted_by list for a rolled card."""
    rolled = session.query(RolledCardModel).filter(RolledCardModel.roll_id == roll_id).first()
    if not rolled:
        return

    attempted_by = rolled.attempted_by or ""
    attempted_list = [u.strip() for u in attempted_by.split(",") if u.strip()]

    if username not in attempted_list:
        attempted_list.append(username)
        rolled.attempted_by = ", ".join(attempted_list)


@with_session(commit=True)
def set_rolled_card_being_rerolled(roll_id: int, being_rerolled: bool, *, session: Session) -> None:
    """Set the being_rerolled status for a rolled card."""
    rolled = session.query(RolledCardModel).filter(RolledCardModel.roll_id == roll_id).first()
    if rolled:
        rolled.being_rerolled = being_rerolled


@with_session(commit=True)
def set_rolled_card_rerolled(
    roll_id: int, new_card_id: Optional[int], original_rarity: Optional[str] = None, *, session: Session
) -> None:
    """Mark a rolled card as having been rerolled."""
    rolled = session.query(RolledCardModel).filter(RolledCardModel.roll_id == roll_id).first()
    if rolled:
        rolled.rerolled = True
        rolled.being_rerolled = False
        rolled.rerolled_card_id = new_card_id
        if original_rarity is not None:
            rolled.original_rarity = original_rarity


@with_session(commit=True)
def set_rolled_card_locked(roll_id: int, is_locked: bool, *, session: Session) -> None:
    """Set the locked status for a rolled card."""
    rolled = session.query(RolledCardModel).filter(RolledCardModel.roll_id == roll_id).first()
    if rolled:
        rolled.is_locked = is_locked


@with_session(commit=True)
def delete_rolled_card(roll_id: int, *, session: Session) -> None:
    """Delete a rolled card entry (use sparingly - prefer reset_rolled_card)."""
    session.query(RolledCardModel).filter(RolledCardModel.roll_id == roll_id).delete()


@with_session
def is_rolled_card_reroll_expired(roll_id: int, *, session: Session) -> bool:
    """Check if the reroll time limit (5 minutes) has expired for a rolled card."""
    rolled = session.query(RolledCardModel).filter(RolledCardModel.roll_id == roll_id).first()
    if not rolled or not rolled.created_at:
        return True

    time_since_creation = datetime.datetime.now(datetime.timezone.utc) - rolled.created_at
    return time_since_creation.total_seconds() > 5 * 60
