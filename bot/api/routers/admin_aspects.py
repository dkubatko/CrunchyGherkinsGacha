"""Admin aspect definition management endpoints.

All routes require a valid admin JWT (``Depends(get_admin_user)``).
"""

import asyncio
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_admin_user
from api.schemas import (
    AdminAspectDefCreateRequest,
    AdminAspectDefResponse,
    AdminAspectDefUpdateRequest,
    AdminBulkAspectDefRequest,
    AdminBulkAspectDefResponse,
)
from repos import aspect_repo
from repos import set_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/aspects", tags=["admin-aspects"])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _definition_to_response(
    defn: "AspectDefinition",
    owned_count: int = 0,
) -> AdminAspectDefResponse:
    """Convert an ``AspectDefinition`` Pydantic DTO to an API response."""
    return AdminAspectDefResponse(
        id=defn.id,
        name=defn.name,
        rarity=defn.rarity,
        set_id=defn.set_id,
        season_id=defn.season_id,
        type_id=defn.type_id,
        created_at=defn.created_at,
        owned_count=owned_count,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get(
    "/sets/{set_id}/season/{season_id}",
    response_model=List[AdminAspectDefResponse],
)
async def list_aspect_definitions_for_set(
    set_id: int,
    season_id: int,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Return all aspect definitions belonging to a set, with per-definition owned counts."""
    defs = await asyncio.to_thread(aspect_repo.get_aspect_definitions_by_set, set_id, season_id)

    results = []
    for d in defs:
        count = await asyncio.to_thread(aspect_repo.get_owned_count_for_definition, d.id)
        results.append(_definition_to_response(d, count))

    return results


@router.post("", response_model=AdminAspectDefResponse, status_code=201)
async def create_aspect_definition(
    body: AdminAspectDefCreateRequest,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Create a single aspect definition."""

    # Validate the target set exists
    target_set = await asyncio.to_thread(set_repo.get_set, body.set_id, body.season_id)
    if target_set is None:
        raise HTTPException(
            status_code=404,
            detail=f"Set {body.set_id} not found in season {body.season_id}",
        )

    # Check for duplicate name within the same set+season
    existing = await asyncio.to_thread(
        aspect_repo.get_aspect_definition_by_name_and_set,
        body.name,
        body.set_id,
        body.season_id,
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Aspect '{body.name}' already exists in set {body.set_id}",
        )

    defn = await asyncio.to_thread(
        aspect_repo.create_aspect_definition,
        set_id=body.set_id,
        name=body.name,
        rarity=body.rarity,
        season_id=body.season_id,
        type_id=body.type_id,
    )
    return _definition_to_response(defn)


@router.put("/{definition_id}", response_model=AdminAspectDefResponse)
async def update_aspect_definition(
    definition_id: int,
    body: AdminAspectDefUpdateRequest,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Update an existing aspect definition's fields."""
    updated = await asyncio.to_thread(
        aspect_repo.update_aspect_definition,
        definition_id,
        name=body.name,
        rarity=body.rarity,
        set_id=body.set_id,
        type_id=body.type_id,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Aspect definition not found")

    count = await asyncio.to_thread(aspect_repo.get_owned_count_for_definition, definition_id)
    return _definition_to_response(updated, count)


@router.delete("/{definition_id}")
async def delete_aspect_definition_endpoint(
    definition_id: int,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Delete an aspect definition. Fails with 409 if it is linked to owned aspects."""
    success, message = await asyncio.to_thread(
        aspect_repo.delete_aspect_definition, definition_id
    )
    if not success:
        status = 404 if "not found" in message.lower() else 409
        raise HTTPException(status_code=status, detail=message)

    return {"status": "deleted", "message": message}


@router.post("/bulk", response_model=AdminBulkAspectDefResponse)
async def bulk_upsert_aspect_definitions(
    body: AdminBulkAspectDefRequest,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Bulk insert or update aspect definitions for a season.

    Existing definitions (matched by ``name + set_id + season_id``) have their
    rarity updated; new ones are inserted.
    """
    items = [item.model_dump() for item in body.definitions]
    count = await asyncio.to_thread(
        aspect_repo.bulk_upsert_aspect_definitions, items, body.season_id
    )
    return AdminBulkAspectDefResponse(upserted=count)


@router.get("/{definition_id}/stats")
async def aspect_definition_stats(
    definition_id: int,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Return usage statistics for a single aspect definition."""
    defn = await asyncio.to_thread(aspect_repo.get_aspect_definition_by_id, definition_id)
    if defn is None:
        raise HTTPException(status_code=404, detail="Aspect definition not found")

    owned_count = await asyncio.to_thread(
        aspect_repo.get_owned_count_for_definition, definition_id
    )
    return {
        "definition_id": defn.id,
        "name": defn.name,
        "rarity": defn.rarity,
        "set_id": defn.set_id,
        "season_id": defn.season_id,
        "owned_count": owned_count,
    }
