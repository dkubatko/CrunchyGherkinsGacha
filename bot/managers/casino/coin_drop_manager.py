"""Coin Drop (Plinko) manager.

Pure functions for selecting buckets and computing payouts. The server is
authoritative for the bucket choice; the client only animates a physics drop
that lands in the server-chosen bucket.

Bucket layout, multipliers, and probabilities are defined in
``settings.constants.COIN_DROP_BUCKETS`` as a list of ``(multiplier, probability)``
tuples in left-to-right order. Probabilities must sum to ~1.0 (validated at
constant load time).

Example expected-value calculation for the current symmetric layout
``10 | 2 | 1 | 0 | 1 | 2 | 10`` with probabilities
``[0.02, 0.05, 0.15, 0.56, 0.15, 0.05, 0.02]``:

    EV = 2 * (0.02 * 10) + 2 * (0.05 * 2) + 2 * (0.15 * 1) + 0
       = 0.4 + 0.2 + 0.3 = 0.9 spins per drop (10% house edge).
"""

from __future__ import annotations

import random
from typing import Tuple

from settings.constants import COIN_DROP_BUCKETS


def roll_bucket() -> Tuple[int, int]:
    """Pick a bucket via weighted random.

    Returns:
        (bucket_index, multiplier) tuple.
    """
    multipliers = [m for m, _ in COIN_DROP_BUCKETS]
    weights = [p for _, p in COIN_DROP_BUCKETS]
    bucket_index = random.choices(range(len(COIN_DROP_BUCKETS)), weights=weights, k=1)[0]
    multiplier = multipliers[bucket_index]
    return bucket_index, multiplier


def compute_payout(bet_amount: int, multiplier: int) -> int:
    """Compute payout for a given bet and bucket multiplier.

    Args:
        bet_amount: Number of spins wagered (typically 1).
        multiplier: Bucket multiplier (e.g., 0, 2, 10).

    Returns:
        Total spins paid out (0 if multiplier is 0).
    """
    return bet_amount * multiplier
