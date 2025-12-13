"""SQLAlchemy session management for the gacha bot database.

This module provides the SQLAlchemy engine, session factory, and context managers
for database operations. It replaces the direct SQLite connection pool with
SQLAlchemy's session management.
"""

from __future__ import annotations

import atexit
import logging
import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker, scoped_session

from settings.constants import DB_PATH
from utils.models import Base

logger = logging.getLogger(__name__)


class SessionConfig:
    """Configuration for SQLAlchemy session management."""

    def __init__(
        self,
        pool_size: int = 6,
        timeout_seconds: int = 30,
        busy_timeout_ms: int = 5000,
    ):
        """
        Initialize session configuration.

        Args:
            pool_size: Size of the connection pool
            timeout_seconds: Connection timeout in seconds
            busy_timeout_ms: SQLite busy timeout in milliseconds
        """
        if pool_size <= 0:
            logger.warning("pool_size must be positive; falling back to 6")
            pool_size = 6
        if timeout_seconds <= 0:
            logger.warning("timeout_seconds must be positive; falling back to 30")
            timeout_seconds = 30
        if busy_timeout_ms <= 0:
            logger.warning("busy_timeout_ms must be positive; falling back to 5000")
            busy_timeout_ms = 5000

        self.pool_size = pool_size
        self.timeout_seconds = timeout_seconds
        self.busy_timeout_ms = busy_timeout_ms


# Global state
_config: Optional[SessionConfig] = None
_engine = None
_session_factory = None
_scoped_session = None


def _get_database_url() -> str:
    """Build the SQLAlchemy database URL for SQLite."""
    # Ensure directory exists
    dir_path = os.path.dirname(DB_PATH)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    return f"sqlite:///{DB_PATH}"


def _configure_sqlite_connection(dbapi_conn, connection_record):
    """Configure SQLite connection with performance and safety pragmas."""
    config = _get_config()
    cursor = dbapi_conn.cursor()
    cursor.execute(f"PRAGMA busy_timeout={config.busy_timeout_ms}")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def _get_config() -> SessionConfig:
    """Get the session configuration, initializing with defaults if needed."""
    global _config
    if _config is None:
        _config = SessionConfig()
        logger.warning("Session not explicitly initialized; using default configuration")
    return _config


def get_engine():
    """Get or create the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        config = _get_config()
        _engine = create_engine(
            _get_database_url(),
            pool_size=config.pool_size,
            pool_timeout=config.timeout_seconds,
            pool_pre_ping=True,
            # SQLite-specific: use StaticPool for thread safety or NullPool for simplicity
            # For SQLite with WAL mode, we can use the default QueuePool
            echo=False,  # Set to True for SQL debugging
        )
        # Register the SQLite configuration handler
        event.listen(_engine, "connect", _configure_sqlite_connection)
        logger.info(
            "SQLAlchemy engine created with pool_size=%d, timeout_seconds=%d",
            config.pool_size,
            config.timeout_seconds,
        )
    return _engine


def get_session_factory():
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,  # Prevent expired object issues after commit
        )
    return _session_factory


def get_scoped_session():
    """Get or create a thread-local scoped session."""
    global _scoped_session
    if _scoped_session is None:
        _scoped_session = scoped_session(get_session_factory())
    return _scoped_session


def initialize_session(
    pool_size: int = 6,
    timeout_seconds: int = 30,
    busy_timeout_ms: int = 5000,
) -> None:
    """
    Initialize session configuration.

    This should be called once at application startup before any database operations.

    Args:
        pool_size: Size of the connection pool (default: 6)
        timeout_seconds: Connection timeout in seconds (default: 30)
        busy_timeout_ms: SQLite busy timeout in milliseconds (default: 5000)
    """
    global _config, _engine, _session_factory, _scoped_session

    # Reset any existing state
    if _scoped_session is not None:
        _scoped_session.remove()
        _scoped_session = None
    if _engine is not None:
        _engine.dispose()
        _engine = None
    _session_factory = None

    _config = SessionConfig(pool_size, timeout_seconds, busy_timeout_ms)
    logger.info(
        "Session initialized with pool_size=%d, timeout_seconds=%d, busy_timeout_ms=%d",
        _config.pool_size,
        _config.timeout_seconds,
        _config.busy_timeout_ms,
    )


@contextmanager
def get_session(commit: bool = False) -> Generator[Session, None, None]:
    """
    Context manager that provides a transactional session.

    Args:
        commit: If True, commits the transaction on successful exit.
                If False, only flushes (for read operations).

    Yields:
        A SQLAlchemy Session instance.

    Example:
        with get_session(commit=True) as session:
            card = CardModel(base_name="Test", ...)
            session.add(card)
    """
    session = get_session_factory()()
    try:
        yield session
        if commit:
            session.commit()
        else:
            session.flush()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_readonly_session() -> Generator[Session, None, None]:
    """
    Context manager for read-only database operations.

    This is a convenience wrapper around get_session(commit=False).

    Yields:
        A SQLAlchemy Session instance.
    """
    with get_session(commit=False) as session:
        yield session


def create_all_tables() -> None:
    """Create all tables defined in the models.

    Note: This should generally not be used in production as Alembic
    handles migrations. This is useful for testing.
    """
    Base.metadata.create_all(get_engine())
    logger.info("All tables created via SQLAlchemy metadata")


def _cleanup_engine() -> None:
    """Cleanup function to dispose of engine connections on exit."""
    global _engine, _scoped_session
    if _scoped_session is not None:
        _scoped_session.remove()
    if _engine is not None:
        _engine.dispose()
        logger.info("SQLAlchemy engine disposed")


# Register cleanup on exit
atexit.register(_cleanup_engine)
