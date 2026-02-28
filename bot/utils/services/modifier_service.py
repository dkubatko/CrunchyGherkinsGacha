"""Modifier service for database operations on modifiers and sets.

This module provides all modifier- and set-related business logic including
CRUD operations for modifiers, querying modifiers by rarity (replacing the
old YAML-based ``load_modifiers_with_sets``), and extended set management
with ``description`` and ``active`` fields.

.. todo::
    Refactor all functions that return ``ModifierModel`` ORM instances to
    return ``Modifier`` Pydantic schemas instead (convert inside the session
    block). This prevents ``DetachedInstanceError`` and keeps the service
    boundary clean. ``get_modifier_by_name_and_rarity`` already does this.

Usage:
    from utils.services import modifier_service

    # Get all active modifiers for the current season grouped by rarity
    by_rarity = modifier_service.get_modifiers_by_rarity(season_id=1)

    # CRUD
    modifier_service.create_modifier(set_id=1, season_id=1, name="Cosmic", rarity="Epic")
    modifier_service.update_modifier(modifier_id=42, name="Galactic")
    modifier_service.delete_modifier(modifier_id=42)
"""

from __future__ import annotations

import datetime
import logging
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from settings.constants import CURRENT_SEASON
from utils.models import CardModel, ModifierCountModel, ModifierModel, SetModel
from utils.schemas import Modifier
from utils.session import get_session

logger = logging.getLogger(__name__)

# ── Rarity ordering (canonical) ──────────────────────────────────────────────
_RARITY_ORDER = ("Common", "Rare", "Epic", "Legendary")


# ─────────────────────────────────────────────────────────────────────────────
# Query helpers
# ─────────────────────────────────────────────────────────────────────────────


def get_modifiers_by_rarity(
    season_id: Optional[int] = None,
    source: Optional[str] = None,
    active_only: bool = True,
) -> Dict[str, List[Modifier]]:
    """Return modifiers grouped by rarity for the given season.

    This is the database-backed replacement for the old
    ``load_modifiers_with_sets()`` that read YAML files.

    Args:
        season_id: Season to query. Defaults to ``CURRENT_SEASON``.
        source: Optional source filter (``"roll"``, ``"slots"``).
                Sets with ``source="all"`` always qualify.
        active_only: If True (default), only include modifiers from active sets.

    Returns:
        Ordered dict mapping rarity name → list of ``Modifier``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session() as session:
        query = (
            session.query(ModifierModel)
            .join(
                SetModel,
                (ModifierModel.set_id == SetModel.id)
                & (ModifierModel.season_id == SetModel.season_id),
            )
            .filter(ModifierModel.season_id == season_id)
        )

        if active_only:
            query = query.filter(SetModel.active.is_(True))

        if source is not None:
            query = query.filter((SetModel.source == "all") | (SetModel.source == source))

        query = query.order_by(ModifierModel.name)
        rows = query.all()

        # Build grouped result
        grouped: Dict[str, List[Modifier]] = {}
        for mod in rows:
            entry = Modifier.from_orm(mod)
            grouped.setdefault(mod.rarity, []).append(entry)

    # Order by canonical rarity, then any extras alphabetically
    ordered: Dict[str, List[Modifier]] = {}
    for rarity in _RARITY_ORDER:
        ordered[rarity] = grouped.pop(rarity, [])
    for rarity in sorted(grouped):
        ordered[rarity] = grouped[rarity]

    return ordered


def get_modifiers_by_set(
    set_id: int,
    season_id: Optional[int] = None,
) -> List[ModifierModel]:
    """Return all modifiers belonging to a set.

    Args:
        set_id: The set's ID within the season.
        season_id: Season to query. Defaults to ``CURRENT_SEASON``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session() as session:
        return (
            session.query(ModifierModel)
            .filter(
                ModifierModel.set_id == set_id,
                ModifierModel.season_id == season_id,
            )
            .order_by(ModifierModel.rarity, ModifierModel.name)
            .all()
        )


def get_modifier_by_id(modifier_id: int) -> Optional[ModifierModel]:
    """Fetch a single modifier by its auto-increment ID."""
    with get_session() as session:
        return session.query(ModifierModel).filter(ModifierModel.id == modifier_id).first()


def get_modifier_by_name_and_set(
    name: str,
    set_id: int,
    season_id: Optional[int] = None,
) -> Optional[ModifierModel]:
    """Lookup a modifier by its keyword name within a specific set.

    Args:
        name: The modifier keyword (case-sensitive).
        set_id: The set ID.
        season_id: Season to query. Defaults to ``CURRENT_SEASON``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session() as session:
        return (
            session.query(ModifierModel)
            .filter(
                ModifierModel.name == name,
                ModifierModel.set_id == set_id,
                ModifierModel.season_id == season_id,
            )
            .first()
        )


def get_modifier_by_name_and_rarity(
    name: str,
    rarity: str,
    season_id: Optional[int] = None,
) -> Optional[Modifier]:
    """Lookup a modifier by keyword and rarity across all sets in a season.

    Useful for resolving a modifier when the set is not known (e.g. from a
    card that only has text fields).

    Args:
        name: The modifier keyword (case-sensitive).
        rarity: The rarity level.
        season_id: Season to query. Defaults to ``CURRENT_SEASON``.

    Returns:
        A ``Modifier`` Pydantic schema with set metadata, or ``None``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session() as session:
        mod = (
            session.query(ModifierModel)
            .options(joinedload(ModifierModel.modifier_set))
            .filter(
                ModifierModel.name == name,
                ModifierModel.rarity == rarity,
                ModifierModel.season_id == season_id,
            )
            .first()
        )
        return Modifier.from_orm(mod) if mod else None


# ─────────────────────────────────────────────────────────────────────────────
# Modifier CRUD
# ─────────────────────────────────────────────────────────────────────────────


def create_modifier(
    set_id: int,
    name: str,
    rarity: str,
    season_id: Optional[int] = None,
) -> ModifierModel:
    """Create a new modifier in the database.

    Args:
        set_id: The set this modifier belongs to.
        name: The modifier keyword.
        rarity: The rarity level (Common / Rare / Epic / Legendary).
        season_id: Season ID. Defaults to ``CURRENT_SEASON``.

    Returns:
        The newly created ``ModifierModel``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    now = datetime.datetime.utcnow().isoformat()

    with get_session(commit=True) as session:
        modifier = ModifierModel(
            set_id=set_id,
            season_id=season_id,
            name=name,
            rarity=rarity,
            created_at=now,
        )
        session.add(modifier)
        session.flush()  # populate modifier.id
        logger.info(
            "Created modifier id=%s name='%s' rarity=%s set=%s season=%s",
            modifier.id,
            name,
            rarity,
            set_id,
            season_id,
        )
        return modifier


def update_modifier(
    modifier_id: int,
    *,
    name: Optional[str] = None,
    rarity: Optional[str] = None,
    set_id: Optional[int] = None,
) -> Optional[ModifierModel]:
    """Update an existing modifier's fields.

    Only provided (non-None) fields are updated.

    Args:
        modifier_id: The modifier to update.
        name: New keyword name.
        rarity: New rarity level.
        set_id: Move modifier to a different set (within the same season).

    Returns:
        The updated ``ModifierModel``, or ``None`` if not found.
    """
    with get_session(commit=True) as session:
        modifier = session.query(ModifierModel).filter(ModifierModel.id == modifier_id).first()
        if not modifier:
            return None

        if name is not None:
            modifier.name = name
        if rarity is not None:
            modifier.rarity = rarity
        if set_id is not None:
            modifier.set_id = set_id

        logger.info(
            "Updated modifier id=%s: name=%s rarity=%s set=%s", modifier_id, name, rarity, set_id
        )
        return modifier


def delete_modifier(modifier_id: int) -> tuple[bool, str]:
    """Delete a modifier if it is not linked to any cards.

    Args:
        modifier_id: The modifier to delete.

    Returns:
        A tuple ``(success: bool, message: str)``.
    """
    with get_session(commit=True) as session:
        modifier = session.query(ModifierModel).filter(ModifierModel.id == modifier_id).first()
        if not modifier:
            return False, "Modifier not found"

        # Check for linked cards
        card_count = (
            session.query(func.count(CardModel.id))
            .filter(CardModel.modifier_id == modifier_id)
            .scalar()
        )
        if card_count and card_count > 0:
            return False, f"Cannot delete: modifier is used by {card_count} card(s)"

        session.delete(modifier)
        logger.info("Deleted modifier id=%s name='%s'", modifier_id, modifier.name)
        return True, "Modifier deleted"


def bulk_upsert_modifiers(
    modifiers: list[dict],
    season_id: Optional[int] = None,
) -> int:
    """Bulk insert or update modifiers.

    Each dict should contain at least ``set_id``, ``name``, ``rarity``.
    If a modifier with the same ``(name, set_id, season_id)`` already
    exists, its rarity is updated; otherwise a new row is inserted.

    Args:
        modifiers: List of modifier dicts.
        season_id: Season ID override. Defaults to ``CURRENT_SEASON``.

    Returns:
        The number of rows inserted or updated.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    now = datetime.datetime.utcnow().isoformat()
    count = 0

    with get_session(commit=True) as session:
        for mod_dict in modifiers:
            set_id = mod_dict["set_id"]
            name = mod_dict["name"]
            rarity = mod_dict["rarity"]

            existing = (
                session.query(ModifierModel)
                .filter(
                    ModifierModel.name == name,
                    ModifierModel.set_id == set_id,
                    ModifierModel.season_id == season_id,
                )
                .first()
            )

            if existing:
                existing.rarity = rarity
            else:
                session.add(
                    ModifierModel(
                        set_id=set_id,
                        season_id=season_id,
                        name=name,
                        rarity=rarity,
                        created_at=now,
                    )
                )
            count += 1

    logger.info("Bulk upserted %d modifiers for season %s", count, season_id)
    return count


def get_card_count_for_modifier(modifier_id: int) -> int:
    """Return the number of cards linked to a modifier."""
    with get_session() as session:
        return (
            session.query(func.count(CardModel.id))
            .filter(CardModel.modifier_id == modifier_id)
            .scalar()
            or 0
        )


# ─────────────────────────────────────────────────────────────────────────────
# Set management (extended from the old set_service)
# ─────────────────────────────────────────────────────────────────────────────


def get_sets_by_season(
    season_id: Optional[int] = None,
    active_only: bool = False,
) -> List[SetModel]:
    """Return all sets for a season, optionally filtering by active status.

    Args:
        season_id: Season to query. Defaults to ``CURRENT_SEASON``.
        active_only: If True, only return sets where ``active=True``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session() as session:
        query = session.query(SetModel).filter(SetModel.season_id == season_id)
        if active_only:
            query = query.filter(SetModel.active.is_(True))
        return query.order_by(SetModel.id).all()


def get_set(
    set_id: int,
    season_id: Optional[int] = None,
) -> Optional[SetModel]:
    """Get a single set by its composite key.

    Args:
        set_id: The set ID.
        season_id: Season to query. Defaults to ``CURRENT_SEASON``.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session() as session:
        return (
            session.query(SetModel)
            .filter(SetModel.id == set_id, SetModel.season_id == season_id)
            .first()
        )


def update_set(
    set_id: int,
    season_id: Optional[int] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    source: Optional[str] = None,
    active: Optional[bool] = None,
) -> Optional[SetModel]:
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
        The updated ``SetModel``, or ``None`` if not found.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session(commit=True) as session:
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
        return set_model


def get_modifier_count_per_set(
    season_id: Optional[int] = None,
) -> Dict[int, int]:
    """Return a mapping of set_id → number of modifiers for the season.

    Useful for dashboard summary views.
    """
    if season_id is None:
        season_id = CURRENT_SEASON

    with get_session() as session:
        rows = (
            session.query(ModifierModel.set_id, func.count(ModifierModel.id))
            .filter(ModifierModel.season_id == season_id)
            .group_by(ModifierModel.set_id)
            .all()
        )
        return {set_id: count for set_id, count in rows}


def get_available_seasons() -> List[int]:
    """Return a sorted list of all season IDs that have sets."""
    with get_session() as session:
        rows = session.query(SetModel.season_id).distinct().order_by(SetModel.season_id).all()
        return [row[0] for row in rows]
