"""Rolled aspect repository for tracking rolled aspect states.

This module mirrors ``rolled_card_repo`` but operates on
``RolledAspectModel`` for aspect rolls.
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from utils.models import RolledAspectModel
from utils.schemas import RolledAspect
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session(commit=True)
def create_rolled_aspect(aspect_id: int, original_roller_id: int, *, session: Session) -> int:
    """Create a rolled aspect entry to track its claim/reroll state.

    Returns the ``roll_id``.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    rolled = RolledAspectModel(
        original_aspect_id=aspect_id,
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
def get_rolled_aspect_by_roll_id(roll_id: int, *, session: Session) -> Optional[RolledAspect]:
    """Get a rolled aspect entry by its roll ID."""
    rolled = (
        session.query(RolledAspectModel).filter(RolledAspectModel.roll_id == roll_id).first()
    )
    return RolledAspect.from_orm(rolled) if rolled else None


@with_session
def get_rolled_aspect_by_aspect_id(aspect_id: int, *, session: Session) -> Optional[RolledAspect]:
    """Get a rolled aspect entry by either original or rerolled aspect ID."""
    rolled = (
        session.query(RolledAspectModel)
        .filter(
            or_(
                RolledAspectModel.original_aspect_id == aspect_id,
                RolledAspectModel.rerolled_aspect_id == aspect_id,
            )
        )
        .first()
    )
    return RolledAspect.from_orm(rolled) if rolled else None


@with_session(commit=True)
def update_rolled_aspect_attempted_by(roll_id: int, username: str, *, session: Session) -> None:
    """Append a username to the attempted_by list for a rolled aspect."""
    rolled = (
        session.query(RolledAspectModel).filter(RolledAspectModel.roll_id == roll_id).first()
    )
    if not rolled:
        return

    attempted_by = rolled.attempted_by or ""
    attempted_list = [u.strip() for u in attempted_by.split(",") if u.strip()]

    if username not in attempted_list:
        attempted_list.append(username)
        rolled.attempted_by = ", ".join(attempted_list)


@with_session(commit=True)
def set_rolled_aspect_being_rerolled(roll_id: int, being_rerolled: bool, *, session: Session) -> None:
    """Set the being_rerolled status for a rolled aspect."""
    rolled = (
        session.query(RolledAspectModel).filter(RolledAspectModel.roll_id == roll_id).first()
    )
    if rolled:
        rolled.being_rerolled = being_rerolled


@with_session(commit=True)
def set_rolled_aspect_rerolled(
    roll_id: int,
    new_aspect_id: Optional[int],
    original_rarity: Optional[str] = None,
    *,
    session: Session,
) -> None:
    """Mark a rolled aspect as having been rerolled."""
    rolled = (
        session.query(RolledAspectModel).filter(RolledAspectModel.roll_id == roll_id).first()
    )
    if rolled:
        rolled.rerolled = True
        rolled.being_rerolled = False
        rolled.rerolled_aspect_id = new_aspect_id
        if original_rarity is not None:
            rolled.original_rarity = original_rarity


@with_session(commit=True)
def set_rolled_aspect_locked(roll_id: int, is_locked: bool, *, session: Session) -> None:
    """Set the locked status for a rolled aspect."""
    rolled = (
        session.query(RolledAspectModel).filter(RolledAspectModel.roll_id == roll_id).first()
    )
    if rolled:
        rolled.is_locked = is_locked


@with_session(commit=True)
def delete_rolled_aspect(roll_id: int, *, session: Session) -> None:
    """Delete a rolled aspect entry."""
    session.query(RolledAspectModel).filter(RolledAspectModel.roll_id == roll_id).delete()


@with_session
def is_rolled_aspect_reroll_expired(roll_id: int, *, session: Session) -> bool:
    """Check if the reroll time limit (5 minutes) has expired."""
    rolled = (
        session.query(RolledAspectModel).filter(RolledAspectModel.roll_id == roll_id).first()
    )
    if not rolled or not rolled.created_at:
        return True

    now = datetime.datetime.now(datetime.timezone.utc)
    elapsed = (now - rolled.created_at).total_seconds()
    return elapsed > 300  # 5 minutes
