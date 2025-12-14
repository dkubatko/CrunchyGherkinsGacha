"""Set service for managing card sets/seasons.

This module provides all set-related business logic including
creating and retrieving card sets.
"""

from __future__ import annotations

import logging
from typing import Optional

from utils.models import SetModel
from utils.session import get_session

logger = logging.getLogger(__name__)


def upsert_set(set_id: int, name: str) -> None:
    """Insert or update a set in the database."""
    with get_session(commit=True) as session:
        existing = session.query(SetModel).filter(SetModel.id == set_id).first()
        if existing:
            existing.name = name
        else:
            new_set = SetModel(id=set_id, name=name)
            session.add(new_set)


def get_set_id_by_name(name: str) -> Optional[int]:
    """Get the set ID for a given set name."""
    with get_session() as session:
        result = session.query(SetModel.id).filter(SetModel.name == name).first()
        return result[0] if result else None
