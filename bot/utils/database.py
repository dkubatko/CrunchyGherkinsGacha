"""Database initialization and Alembic migration helpers.

This module provides database setup, configuration, and migration functionality.
For business logic operations, use the service modules in utils.services/.
"""

import logging
import os
from typing import Optional

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from settings.constants import DATABASE_URL
from utils.session import get_session, get_engine, initialize_session as _init_session

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
ALEMBIC_INI_PATH = os.path.join(PROJECT_ROOT, "alembic.ini")
ALEMBIC_SCRIPT_LOCATION = os.path.join(PROJECT_ROOT, "alembic")
INITIAL_ALEMBIC_REVISION = "20240924_0001"


class DatabaseConfig:
    """Configuration for database connection pool."""

    def __init__(self, pool_size: int = 6, timeout_seconds: int = 30):
        """
        Initialize database configuration.

        Args:
            pool_size: Size of the connection pool
            timeout_seconds: Connection timeout in seconds
        """
        if pool_size <= 0:
            logger.warning("pool_size must be positive; falling back to 6")
            pool_size = 6
        if timeout_seconds <= 0:
            logger.warning("timeout_seconds must be positive; falling back to 30")
            timeout_seconds = 30

        self.pool_size = pool_size
        self.timeout_seconds = timeout_seconds


# Global configuration - will be set by initialize_database()
_db_config: Optional[DatabaseConfig] = None


def initialize_database(pool_size: int = 6, timeout_seconds: int = 30) -> None:
    """
    Initialize database configuration.

    This should be called once at application startup before any database operations.

    Args:
        pool_size: Size of the connection pool (default: 6)
        timeout_seconds: Connection timeout in seconds (default: 30)
    """
    global _db_config
    _db_config = DatabaseConfig(pool_size, timeout_seconds)

    # Also initialize the SQLAlchemy session with the same configuration
    _init_session(pool_size, timeout_seconds)

    logger.info(
        "Database initialized with pool_size=%d, timeout_seconds=%d",
        _db_config.pool_size,
        _db_config.timeout_seconds,
    )


def _get_config() -> DatabaseConfig:
    """Get the database configuration, initializing with defaults if needed."""
    global _db_config
    if _db_config is None:
        _db_config = DatabaseConfig()
        logger.warning("Database not explicitly initialized; using default configuration")
    return _db_config


def _get_alembic_config() -> Config:
    """Build an Alembic configuration pointing at the project's migration setup."""
    config = Config(ALEMBIC_INI_PATH)
    config.set_main_option("script_location", ALEMBIC_SCRIPT_LOCATION)
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    return config


def _has_table(table_name: str) -> bool:
    engine = get_engine()
    insp = inspect(engine)
    return insp.has_table(table_name)


def _create_schema_from_models():
    """Create all tables from current ORM models on a fresh database."""
    from utils.models import Base
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("Schema created from ORM models")


def run_migrations():
    """Apply Alembic migrations to bring the database schema up to date."""
    config = _get_alembic_config()

    # CASE 1: Completely fresh database — no tables at all.
    # Create schema directly from ORM models (always up-to-date) and stamp
    # at head so Alembic considers all historical migrations as already applied.
    if not _has_table("alembic_version") and not _has_table("cards") and not _has_table("user_rolls"):
        logger.info("Fresh database detected; creating schema from models and stamping at head")
        _create_schema_from_models()
        command.stamp(config, "head")
        return

    # CASE 2: Existing schema without Alembic tracking (legacy path from
    # pre-Alembic era). Stamp at the initial revision so the remaining
    # migrations can run incrementally.
    if not _has_table("alembic_version") and (_has_table("cards") or _has_table("user_rolls")):
        logger.info(
            "Existing schema detected without Alembic metadata; stamping baseline revision %s",
            INITIAL_ALEMBIC_REVISION,
        )
        command.stamp(config, INITIAL_ALEMBIC_REVISION)

    # CASE 3: Normal path — run any pending migrations.
    try:
        command.upgrade(config, "head")
    except Exception:
        logger.exception("Failed to apply database migrations")
        raise


def create_tables():
    """Backwards-compatible wrapper that now applies Alembic migrations."""
    run_migrations()


# Run migrations on module import
create_tables()
