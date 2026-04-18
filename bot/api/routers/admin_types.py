"""Admin aspect type management endpoints.

All routes require a valid admin JWT (``Depends(get_admin_user)``).
"""

import asyncio
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_admin_user
from api.schemas import (
    AdminAspectByTypeResponse,
    AdminAspectTypeCreateRequest,
    AdminAspectTypeResponse,
    AdminAspectTypeUpdateRequest,
)
from repos import aspect_type_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/types", tags=["admin-types"])


def _type_to_response(t, count: int) -> AdminAspectTypeResponse:
    return AdminAspectTypeResponse(
        id=t.id,
        name=t.name,
        description=t.description,
        created_at=t.created_at,
        usage_count=count,
    )


@router.get("", response_model=List[AdminAspectTypeResponse])
async def list_types(
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Return all aspect types with usage counts (single GROUP BY query)."""
    rows = await asyncio.to_thread(aspect_type_repo.get_all_types_with_counts)
    return [_type_to_response(t, count) for t, count in rows]


@router.get("/{type_id}/aspects", response_model=List[AdminAspectByTypeResponse])
async def list_aspects_for_type(
    type_id: int,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """List every aspect definition that references this type."""
    # Validate the type exists (helpful 404)
    t = await asyncio.to_thread(aspect_type_repo.get_type_by_id, type_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Type not found")

    rows = await asyncio.to_thread(aspect_type_repo.get_aspects_for_type, type_id)
    return [
        AdminAspectByTypeResponse(
            id=d.id,
            name=d.name,
            rarity=d.rarity,
            set_id=d.set_id,
            set_name=d.aspect_set.name if d.aspect_set else None,
            season_id=d.season_id,
        )
        for d in rows
    ]


@router.post("", response_model=AdminAspectTypeResponse, status_code=201)
async def create_type(
    body: AdminAspectTypeCreateRequest,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Create a new aspect type."""
    try:
        t = await asyncio.to_thread(
            aspect_type_repo.create_type, body.name, body.description
        )
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(
                status_code=409, detail=f"Type '{body.name}' already exists"
            )
        raise
    return _type_to_response(t, 0)


@router.put("/{type_id}", response_model=AdminAspectTypeResponse)
async def update_type(
    type_id: int,
    body: AdminAspectTypeUpdateRequest,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Update an existing aspect type."""
    t = await asyncio.to_thread(
        aspect_type_repo.update_type, type_id, body.name, body.description
    )
    if t is None:
        raise HTTPException(status_code=404, detail="Type not found")
    count = await asyncio.to_thread(aspect_type_repo.get_usage_count, type_id)
    return _type_to_response(t, count)


@router.delete("/{type_id}")
async def delete_type(
    type_id: int,
    _admin: Dict[str, Any] = Depends(get_admin_user),
):
    """Delete an aspect type. Returns 404 if missing, 409 if still referenced."""
    success, message = await asyncio.to_thread(
        aspect_type_repo.delete_type, type_id
    )
    if not success:
        status = 404 if message == "not_found" else 409
        detail = "Type not found" if message == "not_found" else message
        raise HTTPException(status_code=status, detail=detail)
    return {"detail": message}
