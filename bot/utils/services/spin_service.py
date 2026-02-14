"""Spin service for managing user spin balances.

This module provides all spin-related business logic including
retrieving, consuming, and refreshing spin balances, as well as
megaspin tracking and consumption.

Spins are granted via a daily login bonus (claimed from the casino page).
The bonus amount scales with a consecutive-day login streak, with the
progression and daily reset hour configured in config.json.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from typing import Optional
from zoneinfo import ZoneInfo

from utils.events import EventType, DailyBonusOutcome
from utils.models import MegaspinsModel, SpinsModel
from utils.schemas import Megaspins, Spins
from utils.session import get_session

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

PDT_TZ = ZoneInfo("America/Los_Angeles")


def _load_config() -> dict:
    """Load configuration from config.json."""
    config_path = os.path.join(PROJECT_ROOT, "config.json")
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to load config: {e}. Using defaults.")
        return {}


def _get_daily_bonus_config() -> tuple[int, list[int]]:
    """Get daily bonus configuration. Returns (reset_hour_pdt, progression_list)."""
    config = _load_config()
    reset_hour = config.get("DAILY_BONUS_RESET_HOUR_PDT", 6)
    progression = config.get("DAILY_BONUS_PROGRESSION", [10, 15, 20, 25, 30, 35, 40])
    return reset_hour, progression


def _get_bonus_date(dt: datetime.datetime) -> datetime.date:
    """Get the 'bonus date' for a given datetime.

    The bonus day rolls over at DAILY_BONUS_RESET_HOUR_PDT.
    E.g. if reset hour is 6 AM, then 5:59 AM on Feb 14 still counts as Feb 13's bonus day.
    """
    reset_hour, _ = _get_daily_bonus_config()
    pdt_dt = dt.astimezone(PDT_TZ)
    if pdt_dt.hour < reset_hour:
        return (pdt_dt - datetime.timedelta(days=1)).date()
    return pdt_dt.date()


def _get_spins_for_streak(streak: int) -> int:
    """Get the number of spins to grant for a given streak day (1-indexed).

    Uses the progression list from config. If streak exceeds the list length,
    the last value in the progression is used indefinitely.
    """
    _, progression = _get_daily_bonus_config()
    if not progression:
        return 10  # fallback
    index = min(streak - 1, len(progression) - 1)
    return progression[max(0, index)]


def _get_spins_for_megaspin() -> int:
    """Get SPINS_FOR_MEGASPIN from config. Returns the number of spins required for a megaspin.
    In DEBUG_MODE, returns 5 for easier testing.
    """
    from api.config import DEBUG_MODE

    if DEBUG_MODE:
        return 5
    config = _load_config()
    return config.get("SPINS_FOR_MEGASPIN", 100)


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


def get_user_spin_count(user_id: int, chat_id: str) -> int:
    """Get the current spin count for a user in a specific chat. Returns 0 if no record exists."""
    with get_session() as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )
        return spins.count if spins else 0


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
        spins = SpinsModel(
            user_id=user_id,
            chat_id=str(chat_id),
            count=amount,
            login_streak=0,
            last_bonus_date=None,
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


# =============================================================================
# DAILY BONUS FUNCTIONS
# =============================================================================


def get_daily_bonus_status(user_id: int, chat_id: str) -> dict:
    """Check whether the daily bonus is available for a user.

    Returns a dict with:
        available (bool): Whether the user can claim their daily bonus right now.
        current_streak (int): The streak value that would apply if they claim now.
        spins_to_grant (int): How many spins they'd receive.
    """
    now = datetime.datetime.now(PDT_TZ)
    today_bonus_date = _get_bonus_date(now)

    with get_session() as session:
        spins = (
            session.query(SpinsModel)
            .filter(
                SpinsModel.user_id == user_id,
                SpinsModel.chat_id == str(chat_id),
            )
            .first()
        )

    if not spins or not spins.last_bonus_date:
        # Never claimed before → streak starts at 1
        new_streak = 1
        return {
            "available": True,
            "current_streak": new_streak,
            "spins_to_grant": _get_spins_for_streak(new_streak),
        }

    last_date = datetime.date.fromisoformat(spins.last_bonus_date)

    if last_date >= today_bonus_date:
        # Already claimed today
        next_streak = spins.login_streak + 1
        return {
            "available": False,
            "current_streak": spins.login_streak,
            "spins_to_grant": _get_spins_for_streak(next_streak),
        }

    yesterday_bonus_date = today_bonus_date - datetime.timedelta(days=1)
    if last_date == yesterday_bonus_date:
        # Consecutive day → increment streak
        new_streak = spins.login_streak + 1
    else:
        # Streak broken → reset to 1
        new_streak = 1

    return {
        "available": True,
        "current_streak": new_streak,
        "spins_to_grant": _get_spins_for_streak(new_streak),
    }


def claim_daily_bonus(user_id: int, chat_id: str) -> dict:
    """Claim the daily bonus. Atomically grants spins, updates streak and last_bonus_date.

    Returns a dict with:
        success (bool): Whether the claim succeeded.
        spins_granted (int): Number of spins granted (0 if already claimed).
        new_streak (int): Updated streak value.
        total_spins (int): Total spin count after grant.
        message (str): Human-readable status message.
    """
    now = datetime.datetime.now(PDT_TZ)
    today_bonus_date = _get_bonus_date(now)

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
            # First time ever — create record with streak=1
            new_streak = 1
            spins_to_grant = _get_spins_for_streak(new_streak)
            spins = SpinsModel(
                user_id=user_id,
                chat_id=str(chat_id),
                count=spins_to_grant,
                login_streak=new_streak,
                last_bonus_date=today_bonus_date.isoformat(),
            )
            session.add(spins)
            logger.info(
                f"Daily bonus: new user {user_id} in chat {chat_id} → streak {new_streak}, +{spins_to_grant} spins"
            )

            from utils.services import event_service

            event_service.log(
                EventType.DAILY_BONUS,
                DailyBonusOutcome.CLAIMED,
                user_id=user_id,
                chat_id=chat_id,
                streak=new_streak,
                spins_granted=spins_to_grant,
            )

            return {
                "success": True,
                "spins_granted": spins_to_grant,
                "new_streak": new_streak,
                "total_spins": spins.count,
                "message": f"Day {new_streak} bonus! +{spins_to_grant} spins",
            }

        # Check if already claimed today
        if spins.last_bonus_date:
            last_date = datetime.date.fromisoformat(spins.last_bonus_date)
            if last_date >= today_bonus_date:
                return {
                    "success": False,
                    "spins_granted": 0,
                    "new_streak": spins.login_streak,
                    "total_spins": spins.count,
                    "message": "Daily bonus already claimed today",
                }

            yesterday_bonus_date = today_bonus_date - datetime.timedelta(days=1)
            if last_date == yesterday_bonus_date:
                new_streak = spins.login_streak + 1
            else:
                new_streak = 1
        else:
            new_streak = 1

        spins_to_grant = _get_spins_for_streak(new_streak)
        spins.count += spins_to_grant
        spins.login_streak = new_streak
        spins.last_bonus_date = today_bonus_date.isoformat()

        logger.info(
            f"Daily bonus: user {user_id} in chat {chat_id} → streak {new_streak}, +{spins_to_grant} spins (total: {spins.count})"
        )

        from utils.services import event_service

        event_service.log(
            EventType.DAILY_BONUS,
            DailyBonusOutcome.CLAIMED,
            user_id=user_id,
            chat_id=chat_id,
            streak=new_streak,
            spins_granted=spins_to_grant,
        )

        return {
            "success": True,
            "spins_granted": spins_to_grant,
            "new_streak": new_streak,
            "total_spins": spins.count,
            "message": f"Day {new_streak} bonus! +{spins_to_grant} spins",
        }


def consume_user_spin(user_id: int, chat_id: str) -> bool:
    """Consume one spin if available. Returns True if successful, False if no spins available."""
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


# =============================================================================
# MEGASPIN FUNCTIONS
# =============================================================================


def get_user_megaspins(user_id: int, chat_id: str) -> Megaspins:
    """Get or create the megaspin record for a user in a specific chat."""
    spins_for_megaspin = _get_spins_for_megaspin()

    with get_session(commit=True) as session:
        megaspins = (
            session.query(MegaspinsModel)
            .filter(
                MegaspinsModel.user_id == user_id,
                MegaspinsModel.chat_id == str(chat_id),
            )
            .first()
        )

        if not megaspins:
            # Create default megaspins record
            megaspins = MegaspinsModel(
                user_id=user_id,
                chat_id=str(chat_id),
                spins_until_megaspin=spins_for_megaspin,
                megaspin_available=False,
            )
            session.add(megaspins)

        return Megaspins.from_orm(megaspins)


def decrement_megaspin_counter(user_id: int, chat_id: str) -> Megaspins:
    """Decrement the spins_until_megaspin counter by 1 after a regular spin.

    If counter reaches 0 and no megaspin is already available, sets megaspin_available=True.
    Returns the updated Megaspins record.
    """
    spins_for_megaspin = _get_spins_for_megaspin()

    with get_session(commit=True) as session:
        megaspins = (
            session.query(MegaspinsModel)
            .filter(
                MegaspinsModel.user_id == user_id,
                MegaspinsModel.chat_id == str(chat_id),
            )
            .first()
        )

        if not megaspins:
            # Create new record with decremented counter
            megaspins = MegaspinsModel(
                user_id=user_id,
                chat_id=str(chat_id),
                spins_until_megaspin=spins_for_megaspin - 1,
                megaspin_available=False,
            )
            session.add(megaspins)
        else:
            # Only decrement if megaspin is not already available
            # (megaspins can't accrue, so we stop counting once one is available)
            if not megaspins.megaspin_available:
                megaspins.spins_until_megaspin -= 1

                if megaspins.spins_until_megaspin <= 0:
                    megaspins.megaspin_available = True
                    megaspins.spins_until_megaspin = 0
                    logger.info(f"User {user_id} in chat {chat_id} earned a megaspin!")

        return Megaspins.from_orm(megaspins)


def consume_megaspin(user_id: int, chat_id: str) -> bool:
    """Consume a megaspin if available. Returns True if successful, False otherwise."""
    spins_for_megaspin = _get_spins_for_megaspin()

    with get_session(commit=True) as session:
        megaspins = (
            session.query(MegaspinsModel)
            .filter(
                MegaspinsModel.user_id == user_id,
                MegaspinsModel.chat_id == str(chat_id),
            )
            .first()
        )

        if not megaspins or not megaspins.megaspin_available:
            return False

        # Consume the megaspin and reset the counter
        megaspins.megaspin_available = False
        megaspins.spins_until_megaspin = spins_for_megaspin
        logger.info(f"User {user_id} in chat {chat_id} consumed their megaspin")
        return True


def reset_megaspin_counter(user_id: int, chat_id: str) -> Megaspins:
    """Reset the megaspin counter to SPINS_FOR_MEGASPIN and set megaspin_available=False.

    This is typically called after consuming a megaspin.
    """
    spins_for_megaspin = _get_spins_for_megaspin()

    with get_session(commit=True) as session:
        megaspins = (
            session.query(MegaspinsModel)
            .filter(
                MegaspinsModel.user_id == user_id,
                MegaspinsModel.chat_id == str(chat_id),
            )
            .first()
        )

        if not megaspins:
            megaspins = MegaspinsModel(
                user_id=user_id,
                chat_id=str(chat_id),
                spins_until_megaspin=spins_for_megaspin,
                megaspin_available=False,
            )
            session.add(megaspins)
        else:
            megaspins.megaspin_available = False
            megaspins.spins_until_megaspin = spins_for_megaspin

        return Megaspins.from_orm(megaspins)
