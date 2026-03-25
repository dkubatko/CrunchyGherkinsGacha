"""Spin manager — daily bonus and megaspin logic.

Contains streak calculation, bonus date logic, and megaspin state
machine logic.
"""

from __future__ import annotations

import datetime
import logging
from zoneinfo import ZoneInfo

from settings.constants import (
    DAILY_BONUS_PROGRESSION,
    DAILY_BONUS_RESET_HOUR_PDT,
)
from utils.events import EventType, DailyBonusOutcome
from utils.schemas import Megaspins
from utils.session import get_session
from repos import spin_repo

logger = logging.getLogger(__name__)

PDT_TZ = ZoneInfo("America/Los_Angeles")


def _get_bonus_date(dt: datetime.datetime) -> datetime.date:
    """Get the 'bonus date' for a given datetime.

    The bonus day rolls over at DAILY_BONUS_RESET_HOUR_PDT.
    E.g. if reset hour is 6 AM, then 5:59 AM on Feb 14 still counts as Feb 13's bonus day.
    """
    pdt_dt = dt.astimezone(PDT_TZ)
    if pdt_dt.hour < DAILY_BONUS_RESET_HOUR_PDT:
        return (pdt_dt - datetime.timedelta(days=1)).date()
    return pdt_dt.date()


def _get_spins_for_streak(streak: int) -> int:
    """Get the number of spins to grant for a given streak day (1-indexed).

    Uses the progression list from config. If streak exceeds the list length,
    the last value in the progression is used indefinitely.
    """
    if not DAILY_BONUS_PROGRESSION:
        return 10  # fallback
    index = min(streak - 1, len(DAILY_BONUS_PROGRESSION) - 1)
    return DAILY_BONUS_PROGRESSION[max(0, index)]


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
        spins = spin_repo.get_user_spins(user_id, chat_id, session=session)

        if not spins or not spins.last_bonus_date:
            # Never claimed before → streak starts at 1
            new_streak = 1
            return {
                "available": True,
                "current_streak": new_streak,
                "spins_to_grant": _get_spins_for_streak(new_streak),
            }

        last_date = spins.last_bonus_date

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

    event_data = None

    with get_session(commit=True) as session:
        spins = spin_repo.get_user_spins(user_id, chat_id, session=session)

        if not spins:
            # First time ever — create record with streak=1
            new_streak = 1
            spins_to_grant = _get_spins_for_streak(new_streak)
            spins = spin_repo.create_user_spins(
                user_id, chat_id, spins_to_grant, new_streak, today_bonus_date, session=session
            )
            logger.info(
                f"Daily bonus: new user {user_id} in chat {chat_id} → streak {new_streak}, +{spins_to_grant} spins"
            )
            event_data = {"streak": new_streak, "spins_granted": spins_to_grant}
            result = {
                "success": True,
                "spins_granted": spins_to_grant,
                "new_streak": new_streak,
                "total_spins": spins.count,
                "message": f"Day {new_streak} bonus! +{spins_to_grant} spins",
            }
        else:
            # Check if already claimed today
            if spins.last_bonus_date and spins.last_bonus_date >= today_bonus_date:
                result = {
                    "success": False,
                    "spins_granted": 0,
                    "new_streak": spins.login_streak,
                    "total_spins": spins.count,
                    "message": "Daily bonus already claimed today",
                }
            else:
                if spins.last_bonus_date:
                    yesterday_bonus_date = today_bonus_date - datetime.timedelta(days=1)
                    if spins.last_bonus_date == yesterday_bonus_date:
                        new_streak = spins.login_streak + 1
                    else:
                        new_streak = 1
                else:
                    new_streak = 1

                spins_to_grant = _get_spins_for_streak(new_streak)
                new_count = spins.count + spins_to_grant
                spin_repo.update_user_spins(
                    user_id, chat_id,
                    count=new_count,
                    login_streak=new_streak,
                    last_bonus_date=today_bonus_date,
                    session=session,
                )

                logger.info(
                    f"Daily bonus: user {user_id} in chat {chat_id} → streak {new_streak}, +{spins_to_grant} spins (total: {new_count})"
                )
                event_data = {"streak": new_streak, "spins_granted": spins_to_grant}
                result = {
                    "success": True,
                    "spins_granted": spins_to_grant,
                    "new_streak": new_streak,
                    "total_spins": new_count,
                    "message": f"Day {new_streak} bonus! +{spins_to_grant} spins",
                }

    # Emit event after transaction commits
    if event_data:
        from managers import event_manager as event_service

        event_service.log(
            EventType.DAILY_BONUS,
            DailyBonusOutcome.CLAIMED,
            user_id=user_id,
            chat_id=chat_id,
            **event_data,
        )

    return result


def decrement_megaspin_counter(user_id: int, chat_id: str) -> Megaspins:
    """Decrement the spins_until_megaspin counter by 1 after a regular spin.

    If counter reaches 0 and no megaspin is already available, sets megaspin_available=True.
    Returns the updated Megaspins record.
    """
    spins_for_megaspin = spin_repo._get_spins_for_megaspin()

    with get_session(commit=True) as session:
        megaspins = spin_repo.get_user_megaspins(user_id, chat_id, session=session)

        if not megaspins:
            # Create new record with decremented counter
            megaspins = spin_repo.create_user_megaspins(
                user_id,
                chat_id,
                spins_until_megaspin=spins_for_megaspin - 1,
                megaspin_available=False,
                session=session,
            )
        else:
            # Only decrement if megaspin is not already available
            # (megaspins can't accrue, so we stop counting once one is available)
            if not megaspins.megaspin_available:
                new_counter = megaspins.spins_until_megaspin - 1
                new_available = False

                if new_counter <= 0:
                    new_available = True
                    new_counter = 0
                    logger.info(f"User {user_id} in chat {chat_id} earned a megaspin!")

                spin_repo.update_user_megaspins(
                    user_id, chat_id,
                    spins_until_megaspin=new_counter,
                    megaspin_available=new_available,
                    session=session,
                )
                megaspins = Megaspins(
                    user_id=megaspins.user_id,
                    chat_id=megaspins.chat_id,
                    spins_until_megaspin=new_counter,
                    megaspin_available=new_available,
                )

        return megaspins
