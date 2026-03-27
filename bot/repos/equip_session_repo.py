"""Equip session repository for persisting pending equip confirmations."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from utils.models import EquipSessionModel
from utils.session import with_session

logger = logging.getLogger(__name__)


@with_session(commit=True)
def create_or_replace(
    user_id: int,
    chat_id: str,
    aspect_id: int,
    card_id: int,
    name_prefix: str,
    aspect_name: str,
    aspect_rarity: str,
    card_title: str,
    new_title: str,
    *,
    session: Session,
) -> EquipSessionModel:
    """Create or replace a pending equip session for a user+chat pair."""
    existing = (
        session.query(EquipSessionModel)
        .filter(
            EquipSessionModel.user_id == user_id,
            EquipSessionModel.chat_id == chat_id,
        )
        .first()
    )
    if existing:
        existing.aspect_id = aspect_id
        existing.card_id = card_id
        existing.name_prefix = name_prefix
        existing.aspect_name = aspect_name
        existing.aspect_rarity = aspect_rarity
        existing.card_title = card_title
        existing.new_title = new_title
        return existing

    row = EquipSessionModel(
        user_id=user_id,
        chat_id=chat_id,
        aspect_id=aspect_id,
        card_id=card_id,
        name_prefix=name_prefix,
        aspect_name=aspect_name,
        aspect_rarity=aspect_rarity,
        card_title=card_title,
        new_title=new_title,
    )
    session.add(row)
    return row


@with_session
def get_session(
    user_id: int,
    chat_id: str,
    aspect_id: int,
    card_id: int,
    *,
    session: Session,
) -> Optional[EquipSessionModel]:
    """Look up a pending equip session by user, chat, aspect, and card."""
    return (
        session.query(EquipSessionModel)
        .filter(
            EquipSessionModel.user_id == user_id,
            EquipSessionModel.chat_id == chat_id,
            EquipSessionModel.aspect_id == aspect_id,
            EquipSessionModel.card_id == card_id,
        )
        .first()
    )


@with_session(commit=True)
def delete_session(
    user_id: int,
    chat_id: str,
    *,
    session: Session,
) -> None:
    """Delete any pending equip session for a user+chat pair."""
    session.query(EquipSessionModel).filter(
        EquipSessionModel.user_id == user_id,
        EquipSessionModel.chat_id == chat_id,
    ).delete()
