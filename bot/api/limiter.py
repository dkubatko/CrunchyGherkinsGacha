"""
Rate limiter configuration for the API server.

This module provides a global rate limiter instance that can be imported
by any router to apply rate limits to endpoints.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Global rate limiter instance using client IP as the key
limiter = Limiter(key_func=get_remote_address)
