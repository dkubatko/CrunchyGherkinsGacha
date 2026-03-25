"""User manager — business logic for user operations."""

from __future__ import annotations

import logging

from repos import user_repo
from utils.slot_icon import generate_slot_icon

logger = logging.getLogger(__name__)


def update_user_profile(user_id: int, display_name: str, profile_imageb64: str) -> bool:
    """Update user profile with auto-generated slot icon."""
    slot_icon_b64 = generate_slot_icon(profile_imageb64)
    return user_repo.update_user_profile(
        user_id, display_name, profile_imageb64, slot_icon_b64=slot_icon_b64
    )
