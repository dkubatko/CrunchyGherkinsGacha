"""Spin service for managing user spin balances.

This module provides all spin-related business logic including
retrieving, consuming, and refreshing spin balances.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from typing import Optional
from zoneinfo import ZoneInfo

from utils.models import SpinsModel
from utils.schemas import Spins
from utils.session import get_session

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _load_config() -> dict:
    """Load configuration from config.json."""
    config_path = os.path.join(PROJECT_ROOT, "config.json")
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to load config: {e}. Using defaults.")
        return {"SPINS_PER_DAY": 10}


def _get_spins_config() -> tuple[int, int]:
    """Get SPINS_PER_REFRESH and SPINS_REFRESH_HOURS from config. Returns (spins_per_refresh, hours_per_refresh)."""
    config = _load_config()
    return config.get("SPINS_PER_REFRESH", 5), config.get("SPINS_REFRESH_HOURS", 3)


def get_next_spin_refresh(user_id: int, chat_id: str) -> Optional[str]:
    """Get the next refresh time for a user's spins. Returns ISO timestamp or None if user not found."""
    with get_session() as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )

    if not spins or not spins.refresh_timestamp:
        return None

    refresh_timestamp_str = spins.refresh_timestamp
    _, hours_per_refresh = _get_spins_config()

    pdt_tz = ZoneInfo("America/Los_Angeles")

    try:
        if refresh_timestamp_str.endswith("+00:00") or refresh_timestamp_str.endswith("Z"):
            refresh_dt_utc = datetime.datetime.fromisoformat(
                refresh_timestamp_str.replace("Z", "+00:00")
            )
            refresh_dt_pdt = refresh_dt_utc.astimezone(pdt_tz)
        else:
            refresh_dt_naive = datetime.datetime.fromisoformat(
                refresh_timestamp_str.replace("Z", "")
            )
            refresh_dt_pdt = refresh_dt_naive.replace(tzinfo=pdt_tz)

        next_refresh = refresh_dt_pdt + datetime.timedelta(hours=hours_per_refresh)
        return next_refresh.isoformat()
    except (ValueError, TypeError) as e:
        logger.warning(
            f"Invalid refresh_timestamp format for user {user_id} in chat {chat_id}: {e}"
        )
        return None


def get_user_spins(user_id: int, chat_id: str) -> Optional[Spins]:
    """Get the spins record for a user in a specific chat."""
    with get_session() as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )
        return Spins.from_orm(spins) if spins else None


def update_user_spins(user_id: int, chat_id: str, count: int, refresh_timestamp: str) -> bool:
    """Update or insert a spins record for a user in a specific chat."""
    with get_session(commit=True) as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )

        if spins:
            spins.count = count
            spins.refresh_timestamp = refresh_timestamp
        else:
            spins = SpinsModel(
                user_id=user_id,
                chat_id=str(chat_id),
                count=count,
                refresh_timestamp=refresh_timestamp,
            )
            session.add(spins)
        return True


def increment_user_spins(user_id: int, chat_id: str, amount: int = 1) -> Optional[int]:
    """Increment the spin count for a user in a specific chat. Returns new count or None if user not found."""
    with get_session(commit=True) as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )

        if spins:
            spins.count += amount
            return spins.count

        # Create new record if doesn't exist
        current_timestamp = datetime.datetime.now().isoformat()
        spins = SpinsModel(
            user_id=user_id,
            chat_id=str(chat_id),
            count=amount,
            refresh_timestamp=current_timestamp,
        )
        session.add(spins)
        return amount


def decrement_user_spins(user_id: int, chat_id: str, amount: int = 1) -> Optional[int]:
    """Decrement the spin count for a user in a specific chat. Returns new count or None if insufficient spins."""
    with get_session(commit=True) as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )

        if not spins:
            return None

        if spins.count < amount:
            return None

        spins.count -= amount
        return spins.count


def get_or_update_user_spins_with_daily_refresh(user_id: int, chat_id: str) -> int:
    """Get user spins, adding SPINS_PER_REFRESH for each SPINS_REFRESH_HOURS period elapsed. Returns current spins count."""
    pdt_tz = ZoneInfo("America/Los_Angeles")
    current_pdt = datetime.datetime.now(pdt_tz)
    spins_per_refresh, hours_per_refresh = _get_spins_config()

    with get_session(commit=True) as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )

        if not spins:
            current_timestamp = current_pdt.isoformat()
            new_spins = SpinsModel(
                user_id=user_id,
                chat_id=str(chat_id),
                count=spins_per_refresh,
                refresh_timestamp=current_timestamp,
            )
            session.add(new_spins)
            return spins_per_refresh

        current_count = spins.count
        refresh_timestamp_str = spins.refresh_timestamp

        try:
            if refresh_timestamp_str.endswith("+00:00") or refresh_timestamp_str.endswith("Z"):
                refresh_dt_utc = datetime.datetime.fromisoformat(
                    refresh_timestamp_str.replace("Z", "+00:00")
                )
                refresh_dt_pdt = refresh_dt_utc.astimezone(pdt_tz)
            else:
                refresh_dt_naive = datetime.datetime.fromisoformat(
                    refresh_timestamp_str.replace("Z", "")
                )
                refresh_dt_pdt = refresh_dt_naive.replace(tzinfo=pdt_tz)

            time_diff = current_pdt - refresh_dt_pdt
            hours_elapsed = time_diff.total_seconds() / 3600
            periods_elapsed = int(hours_elapsed // hours_per_refresh)

            if periods_elapsed <= 0:
                return current_count

            spins_to_add = periods_elapsed * spins_per_refresh
            new_count = current_count + spins_to_add
            new_refresh_dt = refresh_dt_pdt + datetime.timedelta(
                hours=periods_elapsed * hours_per_refresh
            )
            new_timestamp = new_refresh_dt.isoformat()

            spins.count = new_count
            spins.refresh_timestamp = new_timestamp

            logger.info(
                f"Added {spins_to_add} spins to user {user_id} in chat {chat_id} ({periods_elapsed} periods of {hours_per_refresh}h elapsed)"
            )
            return new_count
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Invalid refresh_timestamp format for user {user_id} in chat {chat_id}: {e}"
            )
            current_timestamp = datetime.datetime.now(ZoneInfo("America/Los_Angeles")).isoformat()
            new_count = current_count + spins_per_refresh
            spins.count = new_count
            spins.refresh_timestamp = current_timestamp
            return new_count


def consume_user_spin(user_id: int, chat_id: str) -> bool:
    """Consume one spin if available. Returns True if successful, False if no spins available."""
    current_count = get_or_update_user_spins_with_daily_refresh(user_id, chat_id)

    if current_count <= 0:
        return False

    with get_session(commit=True) as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )
        if spins and spins.count > 0:
            spins.count -= 1
            return True
        return False
