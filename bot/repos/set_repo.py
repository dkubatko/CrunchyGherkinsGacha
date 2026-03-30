"""Set repository for managing card sets/seasons.

This module provides all set-related data access operations including
creating, retrieving, and updating card sets.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from settings.constants import CURRENT_SEASON
from utils.models import SetModel
from utils.schemas import Set
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session(commit=True)
def upsert_set(
    set_id: int,
    name: str,
    season_id: Optional[int] = None,
    source: str = "all",
    *,
    session: Session,
) -> None:
    """Insert or update a set in the database.

    Args:
        set_id: The set's unique identifier within a season.
        name: The display name of the set.
        season_id: The season this set belongs to. Defaults to CURRENT_SEASON.
        source: The source filter for this set. Can be "roll", "slots", or "all".
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    existing = (
        session.query(SetModel)
        .filter(SetModel.id == set_id, SetModel.season_id == season_id)
        .first()
    )
    if existing:
        existing.name = name
        existing.source = source
    else:
        new_set = SetModel(id=set_id, season_id=season_id, name=name, source=source)
        session.add(new_set)


@with_session
def get_set_by_id(
    set_id: int, season_id: Optional[int] = None, *, session: Session
) -> Optional[Set]:
    """Get a set by its ID and season.

    Args:
        set_id: The set's unique identifier within a season.
        season_id: The season to look in. Defaults to CURRENT_SEASON.

    Returns:
        The Set if found, otherwise None.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    result = (
        session.query(SetModel)
        .filter(SetModel.id == set_id, SetModel.season_id == season_id)
        .first()
    )
    return Set.from_orm(result) if result else None


@with_session
def get_set_id_by_name(
    name: str, season_id: Optional[int] = None, *, session: Session
) -> Optional[int]:
    """Get the set ID for a given set name within a season.

    Args:
        name: The display name of the set.
        season_id: The season to search in. Defaults to CURRENT_SEASON.

    Returns:
        The set ID if found, otherwise None.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    result = (
        session.query(SetModel.id)
        .filter(SetModel.name == name, SetModel.season_id == season_id)
        .first()
    )
    return result[0] if result else None


@with_session
def get_sets_by_season(
    season_id: Optional[int] = None,
    active_only: bool = False,
    *,
    session: Session,
) -> List[Set]:
    """Return all sets for a season, optionally filtering by active status.

    Args:
        season_id: Season to query. Defaults to ``CURRENT_SEASON``.
        active_only: If True, only return sets where ``active=True``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    query = session.query(SetModel).filter(SetModel.season_id == season_id)
    if active_only:
        query = query.filter(SetModel.active.is_(True))
    return [Set.from_orm(r) for r in query.order_by(SetModel.id).all()]


@with_session
def get_set(
    set_id: int,
    season_id: Optional[int] = None,
    *,
    session: Session,
) -> Optional[Set]:
    """Get a single set by its composite key.

    Args:
        set_id: The set ID.
        season_id: Season to query. Defaults to ``CURRENT_SEASON``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    result = (
        session.query(SetModel)
        .filter(SetModel.id == set_id, SetModel.season_id == season_id)
        .first()
    )
    return Set.from_orm(result) if result else None


@with_session(commit=True)
def update_set(
    set_id: int,
    season_id: Optional[int] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    source: Optional[str] = None,
    active: Optional[bool] = None,
    session: Session,
) -> Optional[Set]:
    """Update a set's metadata.

    Only provided (non-None) keyword arguments are applied.

    Args:
        set_id: The set ID.
        season_id: Season to query. Defaults to ``CURRENT_SEASON``.
        name: New display name.
        description: New description text.
        source: New source filter (``"roll"``, ``"slots"``, ``"all"``).
        active: Enable or disable the set.

    Returns:
        The updated ``Set``, or ``None`` if not found.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    set_model = (
        session.query(SetModel)
        .filter(SetModel.id == set_id, SetModel.season_id == season_id)
        .first()
    )
    if not set_model:
        return None

    if name is not None:
        set_model.name = name
    if description is not None:
        set_model.description = description
    if source is not None:
        set_model.source = source
    if active is not None:
        set_model.active = active

    logger.info(
        "Updated set id=%s season=%s: name=%s description=%s source=%s active=%s",
        set_id,
        season_id,
        name,
        description,
        source,
        active,
    )
    return Set.from_orm(set_model)


@with_session
def get_available_seasons(*, session: Session) -> List[int]:
    """Return a sorted list of all season IDs that have sets, always including the current season."""
    rows = session.query(SetModel.season_id).distinct().order_by(SetModel.season_id).all()
    seasons = {row[0] for row in rows}
    seasons.add(CURRENT_SEASON)
    return sorted(seasons)


@with_session
def get_eligible_sets_for_slots(
    season_id: Optional[int] = None,
    *,
    session: Session,
) -> List[Set]:
    """Return active sets eligible for slots (source 'all' or 'slots').

    Args:
        season_id: Season to query. Defaults to ``CURRENT_SEASON``.

    Returns:
        List of eligible ``Set`` objects.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    query = (
        session.query(SetModel)
        .filter(
            SetModel.season_id == season_id,
            SetModel.active.is_(True),
            SetModel.source.in_(["all", "slots"]),
        )
        .order_by(SetModel.id)
    )
    return [Set.from_orm(r) for r in query.all()]
