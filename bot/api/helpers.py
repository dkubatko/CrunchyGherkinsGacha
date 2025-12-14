"""
Helper functions for the API server.

This module provides utility functions used across multiple routers for
data normalization, formatting, and common operations.
"""

import base64
import logging
import urllib.parse
from datetime import datetime, timezone
from typing import List, Optional, Set

from fastapi import HTTPException

from api.config import MINIAPP_URL, get_rarity_weight_pairs, get_rarity_total_weight
from api.schemas import SlotSymbolInfo
from settings.constants import RARITIES
from utils.miniapp import encode_single_card_token

logger = logging.getLogger(__name__)


def normalize_rarity(rarity: Optional[str]) -> Optional[str]:
    """
    Normalize a rarity string to match configured rarity names.

    Args:
        rarity: Raw rarity string from request

    Returns:
        Normalized rarity name or None if not found
    """
    if not rarity:
        return None

    rarity_normalized = rarity.strip().lower()
    for configured_rarity in RARITIES.keys():
        if configured_rarity.lower() == rarity_normalized:
            return configured_rarity
    return None


def decode_image(image_b64: Optional[str]) -> bytes:
    """
    Decode a base64 encoded image.

    Args:
        image_b64: Base64 encoded image string

    Returns:
        Decoded image bytes

    Raises:
        ValueError: If image data is missing or invalid
    """
    if not image_b64:
        raise ValueError("Missing image data")

    try:
        return base64.b64decode(image_b64)
    except Exception as exc:
        raise ValueError("Invalid base64 image data") from exc


def build_single_card_url(card_id: int) -> str:
    """
    Build a URL for viewing a single card in the mini app.

    Args:
        card_id: The card ID to build URL for

    Returns:
        Full URL for viewing the card

    Raises:
        HTTPException: If MINIAPP_URL is not configured
    """
    if not MINIAPP_URL:
        logger.error("MINIAPP_URL not configured; cannot build card link")
        raise HTTPException(status_code=500, detail="Mini app URL not configured")

    share_token = encode_single_card_token(card_id)
    separator = "&" if "?" in MINIAPP_URL else "?"
    return f"{MINIAPP_URL}{separator}startapp={urllib.parse.quote(share_token)}"


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Ensure a datetime is in UTC timezone.

    Args:
        dt: Datetime to normalize

    Returns:
        Datetime in UTC or None
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_timestamp(dt: Optional[datetime]) -> Optional[str]:
    """
    Format a datetime as an ISO 8601 timestamp string.

    Args:
        dt: Datetime to format

    Returns:
        ISO 8601 formatted string with Z suffix for UTC, or None
    """
    normalized = ensure_utc(dt)
    if normalized is None:
        return None

    iso_value = normalized.isoformat()
    if iso_value.endswith("+00:00"):
        return f"{iso_value[:-6]}Z"
    return iso_value


def pick_slot_rarity(random_module) -> str:
    """
    Select a rarity based on configured weights.

    Args:
        random_module: Random module instance for generating random numbers

    Returns:
        Selected rarity name
    """
    rarity_weight_pairs = get_rarity_weight_pairs()
    rarity_total_weight = get_rarity_total_weight()

    if not rarity_weight_pairs or rarity_total_weight <= 0:
        # Fall back to the first configured rarity or Common
        return next(iter(RARITIES.keys()), "Common")

    threshold = random_module.uniform(0, rarity_total_weight)
    cumulative = 0.0
    for name, weight in rarity_weight_pairs:
        cumulative += weight
        if threshold <= cumulative:
            return name

    # Numeric instability fallback
    return rarity_weight_pairs[-1][0]


def generate_slot_loss_pattern(
    random_module, symbols: List[SlotSymbolInfo]
) -> List[SlotSymbolInfo]:
    """
    Generate a dramatic slot machine loss pattern.

    Valid patterns:
    - [a, b, c] (all different) - no matching symbols
    - [a, a, b] (first two same, third different) - creates tension with near-miss

    Invalid patterns:
    - [a, b, a] - too cruel, looks like a near-miss sandwich pattern
    - [a, b, b] - not allowed, must be first two same

    Args:
        random_module: Random module instance for generating random numbers
        symbols: List of available SlotSymbolInfo objects

    Returns:
        List of 3 SlotSymbolInfo objects representing the slot results
    """
    symbol_count = len(symbols)

    if symbol_count < 2:
        # Edge case: if only one symbol exists, just return three of them
        return [symbols[0], symbols[0], symbols[0]]

    # Choose loss pattern type
    pattern_type = random_module.choice(["all_different", "two_same_start"])

    def _weighted_choice_symbol(
        exclude_indices: Set[int], near_target_indices: List[int]
    ) -> SlotSymbolInfo:
        """Pick a symbol favouring those closer to the would-be winning targets."""
        candidates = [idx for idx in range(symbol_count) if idx not in exclude_indices]
        if not candidates:
            return symbols[near_target_indices[0]]

        weights: List[float] = []
        for candidate in candidates:
            min_distance = min(abs(candidate - target) for target in near_target_indices)
            # Invert distance (with +1 to avoid division by zero) to weight near misses higher
            weights.append(1.0 / (min_distance + 1.0))

        total_weight = sum(weights)
        if total_weight <= 0:
            return symbols[random_module.choice(candidates)]

        threshold = random_module.random() * total_weight
        cumulative = 0.0
        for candidate, weight in zip(candidates, weights):
            cumulative += weight
            if cumulative >= threshold:
                return symbols[candidate]

        return symbols[candidates[-1]]

    if pattern_type == "all_different" and symbol_count >= 3:
        # Generate three different symbols with weighted near-miss preference
        first_idx = random_module.randint(0, symbol_count - 1)
        first = symbols[first_idx]
        second = _weighted_choice_symbol({first_idx}, [first_idx])
        second_idx = next(
            i for i, s in enumerate(symbols) if s.id == second.id and s.type == second.type
        )
        third = _weighted_choice_symbol({first_idx, second_idx}, [first_idx, second_idx])
        return [first, second, third]
    else:
        # Generate pattern [a, a, b] - first two same, third different
        same_idx = random_module.randint(0, symbol_count - 1)
        same_symbol = symbols[same_idx]
        different_symbol = _weighted_choice_symbol({same_idx}, [same_idx])
        return [same_symbol, same_symbol, different_symbol]  # [a, a, b]
