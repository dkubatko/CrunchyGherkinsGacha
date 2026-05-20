"""Spin manager — daily bonus and megaspin logic.

Contains streak calculation, bonus date logic, and megaspin state
machine logic.
"""

from __future__ import annotations

import datetime
import logging
import random
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from settings.constants import (
    DAILY_BONUS_PROGRESSION,
    DAILY_BONUS_RESET_HOUR_PDT,
    SLOT_ASPECT_WIN_CHANCE,
    SLOT_BET_MULTIPLIERS,
    SLOT_CARD_WIN_CHANCE,
    SLOT_CLAIM_CHANCE,
)
from utils.events import EventType, DailyBonusOutcome
from utils.rolling import get_random_rarity
from utils.schemas import Megaspins
from utils.session import get_session
from repos import (
    aspect_repo,
    character_repo,
    set_icon_repo,
    set_repo,
    spin_repo,
    spin_result_repo,
    user_repo,
)

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

    Thin wrapper around :func:`decrement_megaspin_counter_by` for legacy
    callers that consume exactly one spin (e.g. the deprecated single-spin
    endpoint kept for backwards-compatibility shims).
    """
    return spin_repo.decrement_megaspin_counter_by(user_id, chat_id, 1)


# ----------------------------------------------------------------------------
# Slot bet / roll orchestration (multi-spin bets, anti-cheat redemption)
# ----------------------------------------------------------------------------


def _slot_probabilities(debug_mode: bool) -> tuple[float, float, float, float]:
    """Return (p_card, p_aspect, p_claim, p_win) for the active config."""
    if debug_mode:
        p_card, p_aspect, p_claim = 0.1, 0.4, 0.2
    else:
        p_card = SLOT_CARD_WIN_CHANCE
        p_aspect = SLOT_ASPECT_WIN_CHANCE
        p_claim = SLOT_CLAIM_CHANCE
    return p_card, p_aspect, p_claim, p_card + p_aspect + p_claim


def _roll_outcome(multiplier: int, debug_mode: bool) -> str:
    """Pick one of {"card", "aspect", "claim", "loss"} weighted for a multi-spin bet.

    Math: ``P(loss|N) = p_loss^N`` (probability of zero wins across N
    independent spins). Conditional on at least one win, the win-type
    distribution is unchanged: ``P(t | any win) = p_t / p_win``.
    """
    p_card, p_aspect, p_claim, p_win = _slot_probabilities(debug_mode)
    p_loss = max(0.0, 1.0 - p_win)
    p_loss_mult = p_loss ** multiplier
    p_win_mult = 1.0 - p_loss_mult
    weights = [
        p_win_mult * (p_card / p_win),
        p_win_mult * (p_aspect / p_win),
        p_win_mult * (p_claim / p_win),
        p_loss_mult,
    ]
    return random.choices(["card", "aspect", "claim", "loss"], weights=weights, k=1)[0]


def _build_loss_results(pool: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build a 3-symbol loss pattern (subset of the patterns in api.helpers).

    We can't reuse :func:`api.helpers.generate_slot_loss_pattern` directly
    because it works on ``SlotSymbolInfo`` dataclasses and weights by index
    proximity. Server-side we only need a valid non-winning triple.
    """
    if not pool:
        return []
    if len(pool) == 1:
        return [pool[0], pool[0], pool[0]]
    pattern = random.choice(["all_different", "two_same_start"])
    if pattern == "two_same_start":
        a = random.choice(pool)
        others = [s for s in pool if not (s["id"] == a["id"] and s["type"] == a["type"])]
        b = random.choice(others)
        return [a, a, b]
    # all_different
    chosen: List[Dict[str, Any]] = []
    remaining = list(pool)
    for _ in range(3):
        if not remaining:
            remaining = list(pool)
        sym = random.choice(remaining)
        chosen.append(sym)
        remaining = [
            s for s in remaining if not (s["id"] == sym["id"] and s["type"] == sym["type"])
        ]
    return chosen


def _resolve_symbol_icon_b64(symbol: Dict[str, Any], *, session) -> Optional[str]:
    """Fetch base64 slot icon for a (user|character|set) symbol.

    Used to embed the winning symbol's icon in the spin response so clients
    can render correctly even if their cached symbol pool is missing the
    pick (e.g. user joined or set was created between symbol load and
    spin). Returns ``None`` for the synthetic claim symbol or when no icon
    is stored — the client falls back to a placeholder.
    """
    stype = symbol.get("type")
    sid = symbol.get("id")
    if stype == "user":
        return user_repo.get_user_slot_icon_b64(sid, session=session)
    if stype == "character":
        return character_repo.get_character_slot_icon_b64(sid, session=session)
    if stype == "set":
        return set_icon_repo.get_icon_b64(sid, session=session)
    # "claim" or unknown — no server-side icon (rendered from a bundled asset).
    return None


def _build_winning_symbol_summary(
    symbol: Dict[str, Any], *, session
) -> Dict[str, Any]:
    """Shape the winning symbol payload (id, type, display_name, slot_icon_b64).

    Returned shape matches :class:`api.schemas.SlotSymbolSummary` for direct
    Pydantic construction at the router layer.
    """
    return {
        "id": symbol["id"],
        "type": symbol["type"],
        "display_name": symbol.get("display_name"),
        "slot_icon_b64": _resolve_symbol_icon_b64(symbol, session=session),
    }


def _build_chat_slot_pools(
    chat_id: str, *, session
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return ``(card_pool, set_pool, claim_pool)`` for slot rolls.

    Each item is a dict with ``{id, display_name, type}``. ``card_pool``
    contains users + characters enrolled in the chat; ``set_pool`` contains
    only sets that have a generated slot icon (so the frontend can render
    them); ``claim_pool`` is the synthetic single-item virtual symbol.
    """
    card_pool = user_repo.get_chat_slot_refs(chat_id, session=session)
    set_pool_full = set_repo.get_eligible_sets_for_slots(session=session)
    set_ids_with_icons = set(set_icon_repo.get_set_ids_with_icons(session=session))
    set_pool: List[Dict[str, Any]] = [
        {"id": s.id, "display_name": s.name, "type": "set"}
        for s in set_pool_full
        if s.id in set_ids_with_icons
    ]
    claim_pool: List[Dict[str, Any]] = [
        {"id": -1, "display_name": "Claim", "type": "claim"}
    ]
    return card_pool, set_pool, claim_pool


def consume_and_roll(
    user_id: int,
    chat_id: str,
    multiplier: int,
    debug_mode: bool,
) -> Dict[str, Any]:
    """Atomically deduct N spins, decrement megaspin progress by N, and roll.

    Returns a dict with the full state needed to build the API response.
    The entire flow runs inside a single committed transaction so a spin
    can never be partially applied (e.g. spins debited but no SpinResult
    persisted).

    Keys returned:
      - ``success`` (bool) — False only on insufficient spins.
      - ``message`` (Optional[str]) — human-readable error on failure.
      - ``spins_remaining`` (int)
      - ``megaspin`` (Megaspins DTO)
      - ``is_win`` (bool)
      - ``slot_results`` (list of ``{"id", "type"}``)
      - ``rarity`` / ``win_type`` / ``set_id`` / ``set_name`` (optional)
      - ``spin_result_id`` (Optional[str]) — present iff ``is_win`` is True.
    """
    if multiplier not in SLOT_BET_MULTIPLIERS:
        raise ValueError(f"Unsupported multiplier: {multiplier}")

    with get_session(commit=True) as session:
        # 1. Atomic balance deduction with FOR UPDATE.
        deducted = spin_repo.consume_user_spins(
            user_id, chat_id, multiplier, session=session
        )
        if not deducted:
            remaining = spin_repo.get_user_spin_count(user_id, chat_id, session=session)
            megaspins = spin_repo.get_user_megaspins(user_id, chat_id, session=session)
            return {
                "success": False,
                "message": f"Insufficient spins for {multiplier}x bet (you have {remaining})",
                "spins_remaining": remaining,
                "megaspin": megaspins,
                "is_win": False,
                "slot_results": [],
                "rarity": None,
                "win_type": None,
                "set_id": None,
                "set_name": None,
                "spin_result_id": None,
                "winning_symbol": None,
            }

        megaspins = spin_repo.decrement_megaspin_counter_by(
            user_id, chat_id, multiplier, session=session
        )
        remaining = spin_repo.get_user_spin_count(user_id, chat_id, session=session)

        # 2. Build server-side symbol pool (no b64 icons — clients have them).
        card_pool, set_pool, claim_pool = _build_chat_slot_pools(
            chat_id, session=session
        )
        full_pool = card_pool + set_pool + claim_pool

        # 3. Roll outcome.
        outcome = _roll_outcome(multiplier, debug_mode)

        winning_symbol: Optional[Dict[str, Any]] = None
        rarity: Optional[str] = None
        win_type: Optional[str] = None
        set_id: Optional[int] = None
        set_name: Optional[str] = None

        if outcome == "card" and card_pool:
            winning_symbol = random.choice(card_pool)
            rarity = get_random_rarity(source="slots")
            win_type = "card"
        elif outcome == "aspect" and set_pool:
            rarity = get_random_rarity(source="slots")
            defs_by_rarity = aspect_repo.get_aspect_definitions_by_rarity(
                source="slots", session=session
            )
            eligible_set_ids = {d.set_id for d in defs_by_rarity.get(rarity, [])}
            eligible = [s for s in set_pool if s["id"] in eligible_set_ids]
            if eligible:
                winning_symbol = random.choice(eligible)
                set_id = winning_symbol["id"]
                set_name = winning_symbol["display_name"]
                win_type = "aspect"
            else:
                rarity = None  # no aspect of this rarity available
        elif outcome == "claim":
            winning_symbol = claim_pool[0]
            win_type = "claim"

        # 4. Build slot_results (3 SlotSymbolInfo-like dicts).
        if winning_symbol:
            slot_results = [winning_symbol, winning_symbol, winning_symbol]
        else:
            slot_results = _build_loss_results(full_pool)

        # 5. Persist SpinResult for non-claim wins (claim wins redeem inline).
        spin_result_id: Optional[str] = None
        if win_type in ("card", "aspect"):
            assert winning_symbol is not None  # for type-checkers
            # Card-win details are derived from the winning symbol; aspect wins
            # carry only set_id/set_name (resolved earlier in this function).
            is_card_win = win_type == "card"
            spin_result = spin_result_repo.create(
                user_id=user_id,
                chat_id=chat_id,
                multiplier=multiplier,
                win_type=win_type,
                rarity=rarity,
                source_type=winning_symbol["type"] if is_card_win else None,
                source_id=winning_symbol["id"] if is_card_win else None,
                display_name=winning_symbol["display_name"] if is_card_win else None,
                set_id=set_id,
                set_name=set_name,
                is_megaspin=False,
            )
            spin_result_id = spin_result.id

        # 6. Resolve full winning-symbol payload (incl. b64 icon) so the
        # client can render correctly even if its cached symbol pool is
        # stale relative to ours.
        winning_symbol_payload: Optional[Dict[str, Any]] = None
        if winning_symbol is not None:
            winning_symbol_payload = _build_winning_symbol_summary(
                winning_symbol, session=session
            )

        return {
            "success": True,
            "message": None,
            "spins_remaining": remaining,
            "megaspin": megaspins,
            "is_win": win_type is not None,
            "slot_results": [
                {"id": s["id"], "type": s["type"]} for s in slot_results
            ],
            "rarity": rarity,
            "win_type": win_type,
            "set_id": set_id,
            "set_name": set_name.title() if set_name else None,
            "spin_result_id": spin_result_id,
            "winning_symbol": winning_symbol_payload,
        }


def consume_megaspin_and_roll(
    user_id: int,
    chat_id: str,
    debug_mode: bool,  # noqa: ARG001 — kept for symmetry with consume_and_roll
) -> Dict[str, Any]:
    """Atomic megaspin: consume one + pick a guaranteed-win symbol + persist.

    Megaspins are always a card/aspect win (no claim, no loss). The
    server-side pool derivation and SpinResult persistence are identical to
    :func:`consume_and_roll` so the front-end + ``/slots/victory`` flows
    are uniform between regular and mega spins (no client-supplied
    win details).

    Returned dict keys match :func:`consume_and_roll` for response reuse:
      - ``success`` (bool) — False only if no megaspin available.
      - ``message`` (Optional[str]).
      - ``spins_remaining`` (Optional[int]) — Megaspins don't touch regular
        spin balance; this is the current count for response convenience.
      - ``megaspin`` (Megaspins DTO).
      - ``is_win`` (bool) — always True on success.
      - ``slot_results`` / ``rarity`` / ``win_type`` / ``set_id`` /
        ``set_name`` / ``spin_result_id`` / ``winning_symbol``.
    """
    with get_session(commit=True) as session:
        # 1. Atomic megaspin consume (FOR UPDATE happens inside spin_repo).
        consumed = spin_repo.consume_megaspin(user_id, chat_id, session=session)
        megaspins = spin_repo.get_user_megaspins(user_id, chat_id, session=session)
        remaining = spin_repo.get_user_spin_count(user_id, chat_id, session=session)

        if not consumed:
            return {
                "success": False,
                "message": "No megaspin available",
                "spins_remaining": remaining,
                "megaspin": megaspins,
                "is_win": False,
                "slot_results": [],
                "rarity": None,
                "win_type": None,
                "set_id": None,
                "set_name": None,
                "spin_result_id": None,
                "winning_symbol": None,
            }

        # 2. Build pool — megaspins never give claim points, so exclude that
        # virtual symbol entirely.
        card_pool, set_pool, _claim_pool = _build_chat_slot_pools(
            chat_id, session=session
        )
        eligible_pool: List[Dict[str, Any]] = card_pool + set_pool
        if not eligible_pool:
            raise RuntimeError(
                f"Megaspin for user {user_id} in chat {chat_id}: empty eligible pool"
            )

        # 3. Pick winning symbol (guaranteed win) and rarity.
        winning_symbol = random.choice(eligible_pool)
        rarity = get_random_rarity(source="slots")

        win_type: str
        set_id: Optional[int] = None
        set_name: Optional[str] = None
        if winning_symbol["type"] == "set":
            win_type = "aspect"
            set_id = winning_symbol["id"]
            set_name = winning_symbol["display_name"]
        else:
            win_type = "card"

        # 4. Persist SpinResult — same shape as regular spins. The
        # ``is_megaspin`` flag drives downstream notification copy.
        is_card_win = win_type == "card"
        spin_result = spin_result_repo.create(
            user_id=user_id,
            chat_id=chat_id,
            multiplier=1,
            win_type=win_type,
            rarity=rarity,
            source_type=winning_symbol["type"] if is_card_win else None,
            source_id=winning_symbol["id"] if is_card_win else None,
            display_name=winning_symbol["display_name"] if is_card_win else None,
            set_id=set_id,
            set_name=set_name,
            is_megaspin=True,
        )

        # 5. Build response — three reels show the winning symbol, plus the
        # full symbol payload for client-side rendering.
        slot_results = [winning_symbol, winning_symbol, winning_symbol]
        winning_symbol_payload = _build_winning_symbol_summary(
            winning_symbol, session=session
        )

        return {
            "success": True,
            "message": None,
            "spins_remaining": remaining,
            "megaspin": megaspins,
            "is_win": True,
            "slot_results": [
                {"id": s["id"], "type": s["type"]} for s in slot_results
            ],
            "rarity": rarity,
            "win_type": win_type,
            "set_id": set_id,
            "set_name": set_name.title() if set_name else None,
            "spin_result_id": spin_result.id,
            "winning_symbol": winning_symbol_payload,
        }

