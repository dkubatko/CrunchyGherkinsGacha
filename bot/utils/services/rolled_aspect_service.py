"""Rolled aspect service for tracking rolled aspect states.

This module mirrors ``rolled_card_service`` but operates on
``RolledAspectModel`` for aspect rolls.
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from sqlalchemy import or_

from utils.models import RolledAspectModel
from utils.schemas import RolledAspect
from utils.session import get_session

logger = logging.getLogger(__name__)


def create_rolled_aspect(aspect_id: int, original_roller_id: int) -> int:
    """Create a rolled aspect entry to track its claim/reroll state.

    Returns the ``roll_id``.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    with get_session(commit=True) as session:
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


def get_rolled_aspect_by_roll_id(roll_id: int) -> Optional[RolledAspect]:
    """Get a rolled aspect entry by its roll ID."""
    with get_session() as session:
        rolled = (
            session.query(RolledAspectModel).filter(RolledAspectModel.roll_id == roll_id).first()
        )
        return RolledAspect.from_orm(rolled) if rolled else None


def get_rolled_aspect_by_aspect_id(aspect_id: int) -> Optional[RolledAspect]:
    """Get a rolled aspect entry by either original or rerolled aspect ID."""
    with get_session() as session:
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


def update_rolled_aspect_attempted_by(roll_id: int, username: str) -> None:
    """Append a username to the attempted_by list for a rolled aspect."""
    with get_session(commit=True) as session:
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


def set_rolled_aspect_being_rerolled(roll_id: int, being_rerolled: bool) -> None:
    """Set the being_rerolled status for a rolled aspect."""
    with get_session(commit=True) as session:
        rolled = (
            session.query(RolledAspectModel).filter(RolledAspectModel.roll_id == roll_id).first()
        )
        if rolled:
            rolled.being_rerolled = being_rerolled


def set_rolled_aspect_rerolled(
    roll_id: int,
    new_aspect_id: Optional[int],
    original_rarity: Optional[str] = None,
) -> None:
    """Mark a rolled aspect as having been rerolled."""
    with get_session(commit=True) as session:
        rolled = (
            session.query(RolledAspectModel).filter(RolledAspectModel.roll_id == roll_id).first()
        )
        if rolled:
            rolled.rerolled = True
            rolled.being_rerolled = False
            rolled.rerolled_aspect_id = new_aspect_id
            if original_rarity is not None:
                rolled.original_rarity = original_rarity


def set_rolled_aspect_locked(roll_id: int, is_locked: bool) -> None:
    """Set the locked status for a rolled aspect."""
    with get_session(commit=True) as session:
        rolled = (
            session.query(RolledAspectModel).filter(RolledAspectModel.roll_id == roll_id).first()
        )
        if rolled:
            rolled.is_locked = is_locked


def delete_rolled_aspect(roll_id: int) -> None:
    """Delete a rolled aspect entry."""
    with get_session(commit=True) as session:
        session.query(RolledAspectModel).filter(RolledAspectModel.roll_id == roll_id).delete()


def is_rolled_aspect_reroll_expired(roll_id: int) -> bool:
    """Check if the reroll time limit (5 minutes) has expired."""
    with get_session() as session:
        rolled = (
            session.query(RolledAspectModel).filter(RolledAspectModel.roll_id == roll_id).first()
        )
        if not rolled or not rolled.created_at:
            return True

        now = datetime.datetime.now(datetime.timezone.utc)
        elapsed = (now - rolled.created_at).total_seconds()
        return elapsed > 300  # 5 minutes
