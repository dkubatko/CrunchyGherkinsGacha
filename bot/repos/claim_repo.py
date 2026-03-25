"""Claim repository for managing claim point balances.

This module provides all claim-related data access operations including
retrieving and modifying claim point balances.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from utils.models import ClaimModel
from utils.schemas import Claim
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session(commit=True)
def _ensure_claim_row_orm(user_id: int, chat_id: str, *, session: Session) -> ClaimModel:
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


@with_session(commit=True)
def get_claim_balance(user_id: int, chat_id: str, *, session: Session) -> int:
    """Get the claim balance for a user in a specific chat."""
    claim = _ensure_claim_row_orm(user_id, str(chat_id), session=session)
    return claim.balance


@with_session(commit=True)
def increment_claim_balance(user_id: int, chat_id: str, amount: int = 1, *, session: Session) -> int:
    """Increment the claim balance for a user. Returns the new balance."""
    if amount <= 0:
        return get_claim_balance(user_id, chat_id, session=session)

    claim = _ensure_claim_row_orm(user_id, str(chat_id), session=session)
    claim.balance += amount
    return claim.balance


@with_session(commit=True)
def reduce_claim_points(user_id: int, chat_id: str, amount: int = 1, *, session: Session) -> Optional[int]:
    """
    Attempt to reduce claim points for a user.

    Returns the remaining balance if successful, or None if insufficient balance.
    """
    if amount <= 0:
        return get_claim_balance(user_id, chat_id, session=session)

    claim = _ensure_claim_row_orm(user_id, str(chat_id), session=session)
    if claim.balance < amount:
        return None  # Insufficient balance

    claim.balance -= amount
    if claim.balance < 0:
        claim.balance = 0
    return claim.balance


@with_session(commit=True)
def set_all_claim_balances_to(balance: int, *, session: Session) -> int:
    """Set all users' claim balances to the specified amount. Returns the number of affected rows."""
    affected = session.query(ClaimModel).update({ClaimModel.balance: balance})
    return affected



@with_session
def get_or_create_claim_for_update(user_id: int, chat_id: str, *, session: Session) -> Claim:
    """Get or create a claim record with row lock for atomic operations."""
    claim = (
        session.query(ClaimModel)
        .filter(
            ClaimModel.user_id == user_id,
            ClaimModel.chat_id == str(chat_id),
        )
        .with_for_update()
        .first()
    )
    if claim is None:
        claim = ClaimModel(user_id=user_id, chat_id=str(chat_id), balance=1)
        session.add(claim)
        session.flush()
    return Claim.from_orm(claim)
