"""Claim service for managing claim point balances.

This module provides all claim-related business logic including
retrieving and modifying claim point balances.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from utils.models import ClaimModel
from utils.session import get_session

logger = logging.getLogger(__name__)


def _ensure_claim_row_orm(session: Session, user_id: int, chat_id: str) -> ClaimModel:
    """Ensure a claim row exists and return it."""
    claim = (
        session.query(ClaimModel)
        .filter(
            ClaimModel.user_id == user_id,
            ClaimModel.chat_id == chat_id,
        )
        .first()
    )

    if claim is None:
        claim = ClaimModel(user_id=user_id, chat_id=chat_id, balance=1)
        session.add(claim)
        session.flush()

    return claim


def get_claim_balance(user_id: int, chat_id: str) -> int:
    """Get the claim balance for a user in a specific chat."""
    with get_session(commit=True) as session:
        claim = _ensure_claim_row_orm(session, user_id, str(chat_id))
        return claim.balance


def increment_claim_balance(user_id: int, chat_id: str, amount: int = 1) -> int:
    """Increment the claim balance for a user. Returns the new balance."""
    if amount <= 0:
        return get_claim_balance(user_id, chat_id)

    with get_session(commit=True) as session:
        claim = _ensure_claim_row_orm(session, user_id, str(chat_id))
        claim.balance += amount
        return claim.balance


def reduce_claim_points(user_id: int, chat_id: str, amount: int = 1) -> Optional[int]:
    """
    Attempt to reduce claim points for a user.

    Returns the remaining balance if successful, or None if insufficient balance.
    """
    if amount <= 0:
        return get_claim_balance(user_id, chat_id)

    with get_session(commit=True) as session:
        claim = _ensure_claim_row_orm(session, user_id, str(chat_id))
        if claim.balance < amount:
            return None  # Insufficient balance

        claim.balance -= amount
        if claim.balance < 0:
            claim.balance = 0
        return claim.balance


def set_all_claim_balances_to(balance: int) -> int:
    """Set all users' claim balances to the specified amount. Returns the number of affected rows."""
    with get_session(commit=True) as session:
        affected = session.query(ClaimModel).update({ClaimModel.balance: balance})
        return affected
