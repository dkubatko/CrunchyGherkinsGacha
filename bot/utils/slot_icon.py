"""Slot icon generation utility.

Uses Google Gemini to generate slot machine icons from profile/character images.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from utils.gemini import GeminiUtil

    GEMINI_AVAILABLE = True
except ImportError:
    logger.warning("GeminiUtil not available. Slot icon generation will be skipped.")
    GEMINI_AVAILABLE = False


def generate_slot_icon(image_b64: str) -> Optional[str]:
    """Generate a slot machine icon from a base64-encoded image.

    Returns the base64-encoded slot icon, or ``None`` if generation failed
    or Gemini is unavailable.
    """
    if not GEMINI_AVAILABLE:
        return None

    try:
        google_api_key = os.getenv("GOOGLE_API_KEY")
        image_gen_model = os.getenv("IMAGE_GEN_MODEL")

        if not google_api_key or not image_gen_model:
            logger.warning(
                "GOOGLE_API_KEY or IMAGE_GEN_MODEL not set, skipping slot icon generation"
            )
            return None

        gemini_util = GeminiUtil(google_api_key, image_gen_model)
        slot_icon_b64 = gemini_util.generate_slot_machine_icon(base_image_b64=image_b64)
        if slot_icon_b64:
            logger.info("Slot machine icon generated successfully")
        else:
            logger.warning("Failed to generate slot machine icon")
        return slot_icon_b64
    except Exception as e:
        logger.error("Error generating slot machine icon: %s", e)
        return None


def generate_set_slot_icon(
    set_name: str, set_description: Optional[str] = None
) -> Optional[str]:
    """Generate a casino-styled slot icon for an aspect set from its theme.

    Returns the base64-encoded slot icon, or ``None`` if generation failed
    or Gemini is unavailable.
    """
    if not GEMINI_AVAILABLE:
        return None

    try:
        google_api_key = os.getenv("GOOGLE_API_KEY")
        image_gen_model = os.getenv("IMAGE_GEN_MODEL")

        if not google_api_key or not image_gen_model:
            logger.warning(
                "GOOGLE_API_KEY or IMAGE_GEN_MODEL not set, skipping set slot icon generation"
            )
            return None

        gemini_util = GeminiUtil(google_api_key, image_gen_model)
        icon_b64 = gemini_util.generate_set_slot_icon(
            set_name=set_name, set_description=set_description
        )
        if icon_b64:
            logger.info("Set slot icon generated successfully for '%s'", set_name)
        else:
            logger.warning("Failed to generate set slot icon for '%s'", set_name)
        return icon_b64
    except Exception as e:
        logger.error("Error generating set slot icon for '%s': %s", set_name, e)
        return None
