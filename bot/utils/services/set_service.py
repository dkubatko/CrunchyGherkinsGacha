"""Set service for managing card sets/seasons.

This module provides all set-related business logic including
creating and retrieving card sets.
"""

from __future__ import annotations

import logging
from typing import Optional

from settings.constants import CURRENT_SEASON
from utils.models import SetModel
from utils.session import get_session

logger = logging.getLogger(__name__)


def upsert_set(set_id: int, name: str, season_id: Optional[int] = None) -> None:
    """Insert or update a set in the database.

    Args:
        set_id: The set's unique identifier within a season.
        name: The display name of the set.
        season_id: The season this set belongs to. Defaults to CURRENT_SEASON.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session(commit=True) as session:
        existing = (
            session.query(SetModel)
            .filter(SetModel.id == set_id, SetModel.season_id == season_id)
            .first()
        )
        if existing:
            existing.name = name
        else:
            new_set = SetModel(id=set_id, season_id=season_id, name=name)
            session.add(new_set)


def get_set_by_id(set_id: int, season_id: Optional[int] = None) -> Optional[SetModel]:
    """Get a set by its ID and season.

    Args:
        set_id: The set's unique identifier within a season.
        season_id: The season to look in. Defaults to CURRENT_SEASON.

    Returns:
        The SetModel if found, otherwise None.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session() as session:
        return (
            session.query(SetModel)
            .filter(SetModel.id == set_id, SetModel.season_id == season_id)
            .first()
        )


def get_set_id_by_name(name: str, season_id: Optional[int] = None) -> Optional[int]:
    """Get the set ID for a given set name within a season.

    Args:
        name: The display name of the set.
        season_id: The season to search in. Defaults to CURRENT_SEASON.

    Returns:
        The set ID if found, otherwise None.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session() as session:
        result = (
            session.query(SetModel.id)
            .filter(SetModel.name == name, SetModel.season_id == season_id)
            .first()
        )
        return result[0] if result else None
