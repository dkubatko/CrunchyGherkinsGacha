"""Admin modifier management endpoints.

All routes require a valid admin JWT (``Depends(get_admin_user)``).
"""

import asyncio
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_admin_user
from api.schemas import (
    AdminBulkModifierRequest,
    AdminBulkModifierResponse,
    AdminModifierCreateRequest,
    AdminModifierResponse,
    AdminModifierUpdateRequest,
)
from utils.services import modifier_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/modifiers", tags=["admin-modifiers"])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _modifier_to_response(mod, card_count: int = 0) -> AdminModifierResponse:
    """Convert a ``ModifierModel`` ORM object to an API response."""
    return AdminModifierResponse(
        id=mod.id,
        name=mod.name,
        rarity=mod.rarity,
        set_id=mod.set_id,
        season_id=mod.season_id,
        created_at=mod.created_at or "",
        card_count=card_count,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get(
    "/sets/{set_id}/season/{season_id}",
    response_model=List[AdminModifierResponse],
)
async def list_modifiers_for_set(
    set_id: int,
    season_id: int,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Return all modifiers belonging to a set, with per-modifier card counts."""
    mods = await asyncio.to_thread(modifier_service.get_modifiers_by_set, set_id, season_id)

    # Batch-fetch card counts (one query per modifier — acceptable for admin views)
    results = []
    for m in mods:
        count = await asyncio.to_thread(modifier_service.get_card_count_for_modifier, m.id)
        results.append(_modifier_to_response(m, count))

    return results


@router.post("", response_model=AdminModifierResponse, status_code=201)
async def create_modifier(
    body: AdminModifierCreateRequest,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Create a single modifier."""
    # Validate the target set exists
    target_set = await asyncio.to_thread(modifier_service.get_set, body.set_id, body.season_id)
    if target_set is None:
        raise HTTPException(
            status_code=404,
            detail=f"Set {body.set_id} not found in season {body.season_id}",
        )

    # Check for duplicate name within the same set+season
    existing = await asyncio.to_thread(
        modifier_service.get_modifier_by_name_and_set, body.name, body.set_id, body.season_id
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Modifier '{body.name}' already exists in set {body.set_id}",
        )

    mod = await asyncio.to_thread(
        modifier_service.create_modifier,
        set_id=body.set_id,
        name=body.name,
        rarity=body.rarity,
        season_id=body.season_id,
    )
    return _modifier_to_response(mod)


@router.put("/{modifier_id}", response_model=AdminModifierResponse)
async def update_modifier(
    modifier_id: int,
    body: AdminModifierUpdateRequest,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Update an existing modifier's fields."""
    updated = await asyncio.to_thread(
        modifier_service.update_modifier,
        modifier_id,
        name=body.name,
        rarity=body.rarity,
        set_id=body.set_id,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Modifier not found")

    count = await asyncio.to_thread(modifier_service.get_card_count_for_modifier, modifier_id)
    return _modifier_to_response(updated, count)


@router.delete("/{modifier_id}")
async def delete_modifier(
    modifier_id: int,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Delete a modifier. Fails with 409 if it is linked to existing cards."""
    success, message = await asyncio.to_thread(modifier_service.delete_modifier, modifier_id)
    if not success:
        status = 404 if "not found" in message.lower() else 409
        raise HTTPException(status_code=status, detail=message)

    return {"status": "deleted", "message": message}


@router.post("/bulk", response_model=AdminBulkModifierResponse)
async def bulk_upsert_modifiers(
    body: AdminBulkModifierRequest,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Bulk insert or update modifiers for a season.

    Existing modifiers (matched by ``name + set_id + season_id``) have their
    rarity updated; new ones are inserted.
    """
    items = [item.model_dump() for item in body.modifiers]
    count = await asyncio.to_thread(modifier_service.bulk_upsert_modifiers, items, body.season_id)
    return AdminBulkModifierResponse(upserted=count)


@router.get("/{modifier_id}/stats")
async def modifier_stats(
    modifier_id: int,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Return usage statistics for a single modifier."""
    mod = await asyncio.to_thread(modifier_service.get_modifier_by_id, modifier_id)
    if mod is None:
        raise HTTPException(status_code=404, detail="Modifier not found")

    card_count = await asyncio.to_thread(modifier_service.get_card_count_for_modifier, modifier_id)
    return {
        "modifier_id": mod.id,
        "name": mod.name,
        "rarity": mod.rarity,
        "set_id": mod.set_id,
        "season_id": mod.season_id,
        "card_count": card_count,
    }
