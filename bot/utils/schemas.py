"""Pydantic schemas (DTOs) for API responses and data transfer.

These schemas are decoupled from the ORM models and provide a clean
interface for serialization, validation, and API responses.
"""

from __future__ import annotations

import base64
import datetime
import html
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

# Forward references for type hints - actual models imported in from_orm methods
# to avoid circular imports


class User(BaseModel):
    """User data transfer object."""

    user_id: int
    username: str
    display_name: Optional[str]
    profile_imageb64: Optional[str]
    slot_iconb64: Optional[str] = None

    @classmethod
    def from_orm(cls, user_orm) -> "User":
        """Convert a UserModel ORM object to a User schema."""
        return cls(
            user_id=user_orm.user_id,
            username=user_orm.username,
            display_name=user_orm.display_name,
            profile_imageb64=user_orm.profile_imageb64,
            slot_iconb64=user_orm.slot_iconb64,
        )


class Card(BaseModel):
    """Card data transfer object (without image data)."""

    id: int
    base_name: str
    modifier: str
    rarity: str
    owner: Optional[str]
    user_id: Optional[int]
    file_id: Optional[str]
    chat_id: Optional[str]
    created_at: Optional[str]
    locked: bool = False
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    set_id: Optional[int] = None

    def title(self, include_id: bool = False, include_rarity: bool = False) -> str:
        """Return the card's title, optionally including rarity and ID.

        Args:
            include_rarity: If True, includes rarity prefix. Default is False.
            include_id: If True, includes card ID in brackets as prefix. Default is False.

        Returns:
            HTML-escaped title text.
        """
        parts = []

        if include_id:
            parts.append(f"[{self.id}]")

        if include_rarity:
            parts.append(self.rarity)

        parts.append(self.modifier)
        parts.append(self.base_name)

        title_text = " ".join(parts).strip()
        return html.escape(title_text)

    @classmethod
    def from_orm(cls, card_orm) -> "Card":
        """Convert a CardModel ORM object to a Card schema."""
        return cls(
            id=card_orm.id,
            base_name=card_orm.base_name,
            modifier=card_orm.modifier,
            rarity=card_orm.rarity,
            owner=card_orm.owner,
            user_id=card_orm.user_id,
            file_id=card_orm.file_id,
            chat_id=card_orm.chat_id,
            created_at=card_orm.created_at,
            locked=card_orm.locked,
            source_type=card_orm.source_type,
            source_id=card_orm.source_id,
            set_id=card_orm.set_id,
        )


class CardWithImage(Card):
    """Card data transfer object with image data included."""

    image_b64: str

    def get_media(self):
        """Return file_id if available, otherwise return decoded base64 image data."""
        if self.file_id:
            return self.file_id
        return base64.b64decode(self.image_b64)

    @classmethod
    def from_orm(cls, card_orm) -> Optional["CardWithImage"]:
        """Convert a CardModel ORM object (with eager-loaded image) to a CardWithImage schema."""
        image_b64 = card_orm.image.image_b64 if card_orm.image else None
        if image_b64 is None:
            image_b64 = ""
        return cls(
            id=card_orm.id,
            base_name=card_orm.base_name,
            modifier=card_orm.modifier,
            rarity=card_orm.rarity,
            owner=card_orm.owner,
            user_id=card_orm.user_id,
            file_id=card_orm.file_id,
            chat_id=card_orm.chat_id,
            created_at=card_orm.created_at,
            locked=card_orm.locked,
            source_type=card_orm.source_type,
            source_id=card_orm.source_id,
            set_id=card_orm.set_id,
            image_b64=image_b64,
        )


class Claim(BaseModel):
    """Claim balance data transfer object."""

    user_id: int
    chat_id: str
    balance: int

    @classmethod
    def from_orm(cls, claim_orm) -> "Claim":
        """Convert a ClaimModel ORM object to a Claim schema."""
        return cls(
            user_id=claim_orm.user_id,
            chat_id=claim_orm.chat_id,
            balance=claim_orm.balance,
        )


class RolledCard(BaseModel):
    """Rolled card state data transfer object."""

    roll_id: int
    original_card_id: int
    rerolled_card_id: Optional[int] = None
    created_at: str
    original_roller_id: int
    rerolled: bool
    being_rerolled: bool
    attempted_by: Optional[str]
    is_locked: bool

    @property
    def current_card_id(self) -> int:
        """Get the current active card ID (rerolled if available, otherwise original)."""
        if self.rerolled and self.rerolled_card_id:
            return self.rerolled_card_id
        return self.original_card_id

    @property
    def card_id(self) -> int:
        """Backward-compatible alias for the active card id."""
        return self.current_card_id

    @classmethod
    def from_orm(cls, rolled_orm) -> "RolledCard":
        """Convert a RolledCardModel ORM object to a RolledCard schema."""
        return cls(
            roll_id=rolled_orm.roll_id,
            original_card_id=rolled_orm.original_card_id,
            rerolled_card_id=rolled_orm.rerolled_card_id,
            created_at=rolled_orm.created_at,
            original_roller_id=rolled_orm.original_roller_id,
            rerolled=rolled_orm.rerolled,
            being_rerolled=rolled_orm.being_rerolled,
            attempted_by=rolled_orm.attempted_by,
            is_locked=rolled_orm.is_locked,
        )


class Character(BaseModel):
    """Character data transfer object."""

    id: int
    chat_id: str
    name: str
    imageb64: str
    slot_iconb64: Optional[str] = None

    @classmethod
    def from_orm(cls, char_orm) -> "Character":
        """Convert a CharacterModel ORM object to a Character schema."""
        return cls(
            id=char_orm.id,
            chat_id=char_orm.chat_id,
            name=char_orm.name,
            imageb64=char_orm.imageb64,
            slot_iconb64=char_orm.slot_iconb64,
        )


class Spins(BaseModel):
    """User spins data transfer object."""

    user_id: int
    chat_id: str
    count: int
    refresh_timestamp: str

    @classmethod
    def from_orm(cls, spins_orm) -> "Spins":
        """Convert a SpinsModel ORM object to a Spins schema."""
        return cls(
            user_id=spins_orm.user_id,
            chat_id=spins_orm.chat_id,
            count=spins_orm.count,
            refresh_timestamp=spins_orm.refresh_timestamp,
        )


class MinesweeperGame(BaseModel):
    """Minesweeper game state data transfer object."""

    id: int
    user_id: int
    chat_id: str
    bet_card_id: int
    bet_card_title: Optional[str] = None
    bet_card_rarity: Optional[str] = None
    mine_positions: List[int]
    claim_point_positions: List[int]
    revealed_cells: List[int]
    status: str
    moves_count: int
    reward_card_id: Optional[int]
    started_timestamp: datetime.datetime
    last_updated_timestamp: datetime.datetime
    source_type: Optional[str] = None
    source_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert game state to dictionary for API responses."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "bet_card_id": self.bet_card_id,
            "mine_positions": self.mine_positions,
            "claim_point_positions": self.claim_point_positions,
            "revealed_cells": self.revealed_cells,
            "status": self.status,
            "moves_count": self.moves_count,
            "reward_card_id": self.reward_card_id,
            "started_timestamp": self.started_timestamp.isoformat(),
            "last_updated_timestamp": self.last_updated_timestamp.isoformat(),
            "source_type": self.source_type,
            "source_id": self.source_id,
        }

    @classmethod
    def from_orm(cls, game_orm) -> "MinesweeperGame":
        """Convert a MinesweeperGameModel ORM object to a MinesweeperGame schema."""
        # Handle JSON fields that may be strings or already parsed
        mine_positions = game_orm.mine_positions
        if isinstance(mine_positions, str):
            mine_positions = json.loads(mine_positions)

        claim_point_positions = game_orm.claim_point_positions
        if isinstance(claim_point_positions, str):
            claim_point_positions = json.loads(claim_point_positions)

        revealed_cells = game_orm.revealed_cells
        if isinstance(revealed_cells, str):
            revealed_cells = json.loads(revealed_cells)

        # Handle timestamps that may be strings or datetime objects
        started_timestamp = game_orm.started_timestamp
        if isinstance(started_timestamp, str):
            started_timestamp = datetime.datetime.fromisoformat(
                started_timestamp.replace("Z", "+00:00")
            )
        elif started_timestamp is not None and started_timestamp.tzinfo is None:
            # Make naive datetime timezone-aware (assume UTC)
            started_timestamp = started_timestamp.replace(tzinfo=datetime.timezone.utc)

        last_updated_timestamp = game_orm.last_updated_timestamp
        if isinstance(last_updated_timestamp, str):
            last_updated_timestamp = datetime.datetime.fromisoformat(
                last_updated_timestamp.replace("Z", "+00:00")
            )
        elif last_updated_timestamp is not None and last_updated_timestamp.tzinfo is None:
            # Make naive datetime timezone-aware (assume UTC)
            last_updated_timestamp = last_updated_timestamp.replace(tzinfo=datetime.timezone.utc)

        return cls(
            id=game_orm.id,
            user_id=game_orm.user_id,
            chat_id=game_orm.chat_id,
            bet_card_id=game_orm.bet_card_id,
            bet_card_title=game_orm.bet_card_title,
            bet_card_rarity=game_orm.bet_card_rarity,
            mine_positions=mine_positions,
            claim_point_positions=claim_point_positions,
            revealed_cells=revealed_cells,
            status=game_orm.status,
            moves_count=game_orm.moves_count,
            reward_card_id=game_orm.reward_card_id,
            started_timestamp=started_timestamp,
            last_updated_timestamp=last_updated_timestamp,
            source_type=game_orm.source_type,
            source_id=game_orm.source_id,
        )
