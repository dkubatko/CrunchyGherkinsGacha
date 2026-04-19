"""Admin set management endpoints.

All routes require a valid admin JWT (``Depends(get_admin_user)``).
"""

import asyncio
import base64
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_admin_user
from api.schemas import (
    AdminSetCreateRequest,
    AdminSetResponse,
    AdminSetUpdateRequest,
)
from repos import aspect_repo
from repos import set_repo
from repos import set_icon_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/sets", tags=["admin-sets"])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _set_to_response(
    set_dto, aspect_count: int = 0, slot_icon_b64: Optional[str] = None
) -> AdminSetResponse:
    """Convert a ``Set`` DTO to an API response."""
    return AdminSetResponse(
        id=set_dto.id,
        season_id=set_dto.season_id,
        name=set_dto.name,
        source=set_dto.source,
        description=set_dto.description,
        active=set_dto.active,
        aspect_count=aspect_count,
        slot_icon_b64=slot_icon_b64,
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
    """Return all sets for a season, with aspect counts and slot icons."""
    sets = await asyncio.to_thread(set_repo.get_sets_by_season, season_id, False)
    counts = await asyncio.to_thread(aspect_repo.get_aspect_definition_count_per_set, season_id)
    icons = await asyncio.to_thread(set_icon_repo.get_all_icons_b64, season_id)

    return [
        _set_to_response(s, counts.get(s.id, 0), icons.get(s.id))
        for s in sets
    ]


@router.post("/seasons/{season_id}", response_model=AdminSetResponse, status_code=201)
async def create_set(
    season_id: int,
    body: AdminSetCreateRequest,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Create a new set within a season.

    The set ID is auto-assigned as ``max(existing IDs) + 1`` for the season.
    A slot icon is generated synchronously via Gemini before returning.
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

    # Generate slot icon synchronously (frontend waits with a spinner)
    slot_icon_b64 = await asyncio.to_thread(
        _generate_and_store_icon, new_set.id, new_set.season_id,
        new_set.name, body.description or None,
    )

    return _set_to_response(new_set, slot_icon_b64=slot_icon_b64)


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
    icon_b64 = await asyncio.to_thread(set_icon_repo.get_icon_b64, set_id, season_id)
    return _set_to_response(updated, counts.get(set_id, 0), icon_b64)


@router.delete("/seasons/{season_id}/{set_id}", status_code=204)
async def delete_set_endpoint(
    season_id: int,
    set_id: int,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Delete an empty set. Fails if the set still has aspect definitions."""

    def _do_delete():
        # Delete slot icon first (set_icons has FK to sets).
        try:
            set_icon_repo.delete_icon(set_id, season_id)
        except Exception:
            logger.exception("Failed to delete slot icon for set %s/%s", set_id, season_id)
        try:
            deleted = set_repo.delete_set(set_id, season_id)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        if not deleted:
            raise HTTPException(status_code=404, detail="Set not found")

    await asyncio.to_thread(_do_delete)
    return None


@router.post("/seasons/{season_id}/{set_id}/regenerate-icon", response_model=AdminSetResponse)
async def regenerate_set_icon(
    season_id: int,
    set_id: int,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Regenerate the slot icon for an existing set."""
    set_dto = await asyncio.to_thread(set_repo.get_set, set_id, season_id)
    if set_dto is None:
        raise HTTPException(status_code=404, detail="Set not found")

    slot_icon_b64 = await asyncio.to_thread(
        _generate_and_store_icon, set_id, season_id,
        set_dto.name, set_dto.description or None,
    )

    counts = await asyncio.to_thread(aspect_repo.get_aspect_definition_count_per_set, season_id)
    return _set_to_response(set_dto, counts.get(set_id, 0), slot_icon_b64)


# ── Internal ─────────────────────────────────────────────────────────────────


def _generate_and_store_icon(
    set_id: int,
    season_id: int,
    set_name: str,
    set_description: Optional[str],
) -> Optional[str]:
    """Generate a set slot icon and persist it. Returns base64 or ``None``."""
    from utils.slot_icon import generate_set_slot_icon

    icon_b64 = generate_set_slot_icon(set_name, set_description)
    if icon_b64:
        set_icon_repo.upsert_icon(set_id, season_id, base64.b64decode(icon_b64))
    return icon_b64
