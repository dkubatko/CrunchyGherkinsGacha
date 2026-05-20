"""
Async Redis client singleton.

Provides a process-wide ``redis.asyncio.Redis`` connection used for ephemeral,
TTL-keyed state that doesn't belong in PostgreSQL (e.g. short-lived handshake
tokens, rate-limit counters, pub/sub signals).

Lifecycle:
    * Call :func:`init_redis` once during process startup (FastAPI startup
      hook, bot post_init, …). It establishes the connection pool and runs a
      ``PING`` so the process fails fast if Redis is misconfigured.
    * Use :func:`get_redis` from anywhere to obtain the live client.
    * Call :func:`close_redis` on shutdown to release the pool.

Configuration:
    * ``REDIS_URL`` environment variable (required — no default). The process
      will refuse to start if it's missing so misconfiguration surfaces at
      boot rather than at first use.
    * Local native dev: ``REDIS_URL=redis://localhost:6379/0``
    * Docker / production: ``REDIS_URL=redis://redis:6379/0`` (compose service)

This module is intentionally side-effect free at import time. Nothing connects
until :func:`init_redis` is called.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from redis import asyncio as redis_asyncio
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

_client: Optional[redis_asyncio.Redis] = None


def _redis_url() -> str:
    url = os.getenv("REDIS_URL")
    if not url:
        raise RuntimeError(
            "REDIS_URL environment variable is not set. Configure it in your "
            ".env (e.g. redis://localhost:6379/0 for native dev or "
            "redis://redis:6379/0 for Docker Compose)."
        )
    return url


async def init_redis() -> redis_asyncio.Redis:
    """
    Initialize the singleton Redis client and verify connectivity.

    Safe to call multiple times — subsequent calls return the existing client
    without re-pinging. Raises :class:`RedisError` if the initial ping fails
    so a misconfigured deployment surfaces immediately at startup.
    """
    global _client
    if _client is not None:
        return _client

    url = _redis_url()
    client = redis_asyncio.from_url(
        url,
        encoding="utf-8",
        decode_responses=True,
        socket_timeout=5,
        socket_connect_timeout=5,
        health_check_interval=30,
    )
    try:
        pong = await client.ping()
        if not pong:
            raise RedisError("Redis PING returned a falsy response")
    except Exception:
        # Release the half-initialized client so a retry can rebuild it.
        try:
            await client.aclose()
        except Exception:
            pass
        logger.exception("Failed to connect to Redis at %s", url)
        raise

    _client = client
    logger.info("🟥 Connected to Redis at %s", url)
    return _client


def get_redis() -> redis_asyncio.Redis:
    """
    Return the live Redis client.

    Raises :class:`RuntimeError` if :func:`init_redis` has not been called yet —
    callers should never receive a half-initialized client.
    """
    if _client is None:
        raise RuntimeError(
            "Redis client has not been initialized. Call init_redis() during "
            "process startup before using Redis."
        )
    return _client


async def close_redis() -> None:
    """Tear down the singleton client. No-op if not initialized."""
    global _client
    if _client is None:
        return
    try:
        await _client.aclose()
    except Exception:
        logger.warning("Error while closing Redis client", exc_info=True)
    finally:
        _client = None

