"""
RTB (Ride the Bus) module wrapper.

This module provides a consistent interface for RTB functionality,
matching the pattern used by other utils modules like minesweeper.
"""

from utils.services.rtb_service import set_debug_mode

__all__ = ["set_debug_mode"]
