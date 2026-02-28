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
from utils.services import modifier_service, set_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/sets", tags=["admin-sets"])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _set_to_response(set_model, modifier_count: int = 0) -> AdminSetResponse:
    """Convert a ``SetModel`` ORM object to an API response."""
    return AdminSetResponse(
        id=set_model.id,
        season_id=set_model.season_id,
        name=set_model.name,
        source=set_model.source,
        description=set_model.description,
        active=set_model.active,
        modifier_count=modifier_count,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/seasons", response_model=List[int])
async def list_seasons(
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Return all season IDs that have at least one set."""
    return await asyncio.to_thread(modifier_service.get_available_seasons)


@router.get("/seasons/{season_id}", response_model=List[AdminSetResponse])
async def list_sets(
    season_id: int,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Return all sets for a season, with modifier counts."""
    sets = await asyncio.to_thread(modifier_service.get_sets_by_season, season_id, False)
    counts = await asyncio.to_thread(modifier_service.get_modifier_count_per_set, season_id)

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
        existing = modifier_service.get_sets_by_season(season_id, active_only=False)
        next_id = max((s.id for s in existing), default=0) + 1
        set_service.upsert_set(
            set_id=next_id,
            name=body.name,
            season_id=season_id,
            source=body.source,
        )
        # Apply description and active via modifier_service.update_set which
        # handles the extended fields added in the modifiers migration.
        if body.description or not body.active:
            modifier_service.update_set(
                next_id,
                season_id,
                description=body.description or None,
                active=body.active if not body.active else None,
            )
        return modifier_service.get_set(next_id, season_id)

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
        return modifier_service.update_set(
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

    counts = await asyncio.to_thread(modifier_service.get_modifier_count_per_set, season_id)
    return _set_to_response(updated, counts.get(set_id, 0))
