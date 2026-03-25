"""Admin set management endpoints.

All routes require a valid admin JWT (``Depends(get_admin_user)``).
"""

import asyncio
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_admin_user
from api.schemas import (
    AdminSetCreateRequest,
    AdminSetResponse,
    AdminSetUpdateRequest,
)
from repos import aspect_repo
from repos import set_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/sets", tags=["admin-sets"])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _set_to_response(set_dto, aspect_count: int = 0) -> AdminSetResponse:
    """Convert a ``Set`` DTO to an API response."""
    return AdminSetResponse(
        id=set_dto.id,
        season_id=set_dto.season_id,
        name=set_dto.name,
        source=set_dto.source,
        description=set_dto.description,
        active=set_dto.active,
        aspect_count=aspect_count,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/seasons", response_model=List[int])
async def list_seasons(
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Return all season IDs that have at least one set."""
    return await asyncio.to_thread(set_repo.get_available_seasons)


@router.get("/seasons/{season_id}", response_model=List[AdminSetResponse])
async def list_sets(
    season_id: int,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Return all sets for a season, with modifier counts."""
    sets = await asyncio.to_thread(set_repo.get_sets_by_season, season_id, False)
    counts = await asyncio.to_thread(aspect_repo.get_aspect_definition_count_per_set, season_id)

    return [_set_to_response(s, counts.get(s.id, 0)) for s in sets]


@router.post("/seasons/{season_id}", response_model=AdminSetResponse, status_code=201)
async def create_set(
    season_id: int,
    body: AdminSetCreateRequest,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Create a new set within a season.

    The set ID is auto-assigned as ``max(existing IDs) + 1`` for the season.
    """

    def _do_create():
        existing = set_repo.get_sets_by_season(season_id, active_only=False)
        next_id = max((s.id for s in existing), default=0) + 1
        set_repo.upsert_set(
            set_id=next_id,
            name=body.name,
            season_id=season_id,
            source=body.source,
        )
        # Apply description and active via update_set
        if body.description or not body.active:
            set_repo.update_set(
                next_id,
                season_id,
                description=body.description or None,
                active=body.active if not body.active else None,
            )
        return set_repo.get_set(next_id, season_id)

    new_set = await asyncio.to_thread(_do_create)
    if new_set is None:
        raise HTTPException(status_code=500, detail="Failed to create set")

    return _set_to_response(new_set)


@router.put("/seasons/{season_id}/{set_id}", response_model=AdminSetResponse)
async def update_set(
    season_id: int,
    set_id: int,
    body: AdminSetUpdateRequest,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Update an existing set's metadata."""

    def _do_update():
        return set_repo.update_set(
            set_id,
            season_id,
            name=body.name,
            description=body.description,
            source=body.source,
            active=body.active,
        )

    updated = await asyncio.to_thread(_do_update)
    if updated is None:
        raise HTTPException(status_code=404, detail="Set not found")

    counts = await asyncio.to_thread(aspect_repo.get_aspect_definition_count_per_set, season_id)
    return _set_to_response(updated, counts.get(set_id, 0))
