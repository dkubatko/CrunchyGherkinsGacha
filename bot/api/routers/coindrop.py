"""Coin Drop (Plinko) game API endpoints.

Stateless game: each tap is an independent request that atomically deducts 1
spin, picks a bucket via weighted RNG (server-authoritative), credits payout,
logs an event, and (on jackpot) fires a chat notification.
"""

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from api.background_tasks import process_coin_drop_jackpot_notification
from api.dependencies import (
    get_validated_user,
    validate_user_in_chat,
    verify_user_match,
)
from api.schemas import (
    CoinDropBucketInfo,
    CoinDropConfigResponse,
    CoinDropDropRequest,
    CoinDropResultResponse,
)
from managers import event_manager
from managers.casino import coin_drop_manager
from repos import spin_repo, user_repo
from settings.constants import COIN_DROP_BUCKETS, COIN_DROP_PEG_ROWS
from utils.events import CoinDropOutcome, EventType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/coindrop", tags=["coindrop"])

BET_AMOUNT = 1
JACKPOT_MULTIPLIER = 10  # multipliers >= this trigger the chat announcement


@router.get("/config", response_model=CoinDropConfigResponse)
async def get_coin_drop_config():
    """Return public Coin Drop config (peg rows + bucket multipliers L→R)."""
    return CoinDropConfigResponse(
        peg_rows=COIN_DROP_PEG_ROWS,
        buckets=[CoinDropBucketInfo(multiplier=m) for m, _ in COIN_DROP_BUCKETS],
    )


@router.post("/drop", response_model=CoinDropResultResponse)
async def drop_coin(
    request: CoinDropDropRequest,
    validated_user: Dict[str, Any] = Depends(get_validated_user),
):
    """Drop one coin: deduct 1 spin, pick bucket, credit payout."""
    await verify_user_match(request.user_id, validated_user)
    chat_id = str(request.chat_id).strip()
    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id is required")
    await validate_user_in_chat(request.user_id, chat_id)

    new_balance = await asyncio.to_thread(
        spin_repo.decrement_user_spins, request.user_id, chat_id, BET_AMOUNT
    )
    if new_balance is None:
        event_manager.log(
            EventType.COIN_DROP,
            CoinDropOutcome.INSUFFICIENT,
            user_id=request.user_id,
            chat_id=chat_id,
            bet_amount=BET_AMOUNT,
        )
        raise HTTPException(status_code=400, detail="Not enough spins")

    try:
        bucket_index, multiplier = coin_drop_manager.roll_bucket()
        payout = coin_drop_manager.compute_payout(BET_AMOUNT, multiplier)
    except Exception as exc:
        # Refund on unexpected RNG/config error.
        await asyncio.to_thread(
            spin_repo.increment_user_spins, request.user_id, chat_id, BET_AMOUNT
        )
        event_manager.log(
            EventType.COIN_DROP,
            CoinDropOutcome.ERROR,
            user_id=request.user_id,
            chat_id=chat_id,
            error=str(exc),
        )
        logger.exception("Coin Drop roll failed for user %s", request.user_id)
        raise HTTPException(status_code=500, detail="Coin Drop failed; spin refunded") from exc

    if payout > 0:
        new_balance = await asyncio.to_thread(
            spin_repo.increment_user_spins, request.user_id, chat_id, payout
        )

    outcome = CoinDropOutcome.WON if payout > 0 else CoinDropOutcome.LOST

    event_manager.log(
        EventType.COIN_DROP,
        outcome,
        user_id=request.user_id,
        chat_id=chat_id,
        bet_amount=BET_AMOUNT,
        bucket_index=bucket_index,
        multiplier=multiplier,
        payout=payout,
    )

    if multiplier >= JACKPOT_MULTIPLIER:
        username = await asyncio.to_thread(user_repo.get_username_for_user_id, request.user_id)
        if username:
            asyncio.create_task(
                process_coin_drop_jackpot_notification(
                    username=username,
                    chat_id=chat_id,
                    multiplier=multiplier,
                )
            )

    return CoinDropResultResponse(
        bucket_index=bucket_index,
        multiplier=multiplier,
        payout=payout,
        spins_balance=new_balance,
    )
