"""User manager — business logic for user operations."""

from __future__ import annotations

import logging
from typing import NamedTuple

from repos import user_repo
from utils.slot_icon import generate_slot_icon

logger = logging.getLogger(__name__)


class ProfileUpdateResult(NamedTuple):
    """Result of a profile update operation."""
    profile_saved: bool
    slot_icon_generated: bool


def update_user_profile(user_id: int, display_name: str, profile_imageb64: str) -> ProfileUpdateResult:
    """Update user profile with auto-generated slot icon.

    Returns a ``ProfileUpdateResult`` indicating whether the profile was saved
    and whether the slot icon was generated successfully.
    """
    slot_icon_b64 = generate_slot_icon(profile_imageb64)
    saved = user_repo.update_user_profile(
        user_id, display_name, profile_imageb64, slot_icon_b64=slot_icon_b64
    )
    return ProfileUpdateResult(
        profile_saved=saved,
        slot_icon_generated=slot_icon_b64 is not None,
    )
