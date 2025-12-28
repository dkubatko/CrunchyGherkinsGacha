"""SQLAlchemy ORM models for the gacha bot database.

This module defines all database tables using SQLAlchemy declarative ORM.
Each model corresponds to a table in the SQLite database.
"""

from __future__ import annotations

import datetime
import html
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:
    pass


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class CardModel(Base):
    """Represents a gacha card in the database."""

    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_name: Mapped[str] = mapped_column(Text, nullable=False)
    modifier: Mapped[str] = mapped_column(Text, nullable=False)
    rarity: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chat_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    set_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    season_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationship to card images (one-to-one)
    image: Mapped[Optional["CardImageModel"]] = relationship(
        "CardImageModel", back_populates="card", uselist=False, cascade="all, delete-orphan"
    )

    # Relationship to set (composite FK: set_id + season_id)
    card_set: Mapped[Optional["SetModel"]] = relationship(
        "SetModel",
        back_populates="cards",
        foreign_keys="[CardModel.set_id, CardModel.season_id]",
        primaryjoin="and_(CardModel.set_id == SetModel.id, CardModel.season_id == SetModel.season_id)",
    )

    # Indices for performance
    __table_args__ = (
        ForeignKeyConstraint(
            ["set_id", "season_id"],
            ["sets.id", "sets.season_id"],
            name="fk_cards_set_season",
        ),
        Index("idx_cards_chat_id", "chat_id"),
        Index("idx_cards_user_id", "user_id"),
        Index("idx_cards_owner", "owner"),
        Index("idx_cards_rarity", "rarity"),
        Index("idx_cards_season_id", "season_id"),
        Index("idx_cards_season_user", "season_id", "user_id"),
    )

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


class CardImageModel(Base):
    """Stores card image data separately for performance."""

    __tablename__ = "card_images"

    card_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cards.id", ondelete="CASCADE"), primary_key=True
    )
    image_b64: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_thumb_b64: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship back to card
    card: Mapped["CardModel"] = relationship("CardModel", back_populates="image")

    __table_args__ = (Index("idx_card_images_card_id", "card_id"),)


class UserModel(Base):
    """Represents a Telegram user registered with the bot."""

    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    profile_imageb64: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    slot_iconb64: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship to chat memberships
    chat_memberships: Mapped[List["ChatModel"]] = relationship(
        "ChatModel", back_populates="user", cascade="all, delete-orphan"
    )


class ChatModel(Base):
    """Represents a user's membership in a chat (many-to-many relationship)."""

    __tablename__ = "chats"

    chat_id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id"), primary_key=True)

    # Relationship to user
    user: Mapped["UserModel"] = relationship("UserModel", back_populates="chat_memberships")


class ClaimModel(Base):
    """Tracks claim point balances per user per chat."""

    __tablename__ = "claims"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[str] = mapped_column(Text, primary_key=True)
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class UserRollModel(Base):
    """Tracks when users last rolled in each chat."""

    __tablename__ = "user_rolls"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[str] = mapped_column(Text, primary_key=True)
    last_roll_timestamp: Mapped[str] = mapped_column(Text, nullable=False)


class RolledCardModel(Base):
    """Tracks the state of rolled cards (for reroll mechanics)."""

    __tablename__ = "rolled_cards"

    roll_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    original_card_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    rerolled_card_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    original_roller_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rerolled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    being_rerolled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempted_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    original_rarity: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_rolled_cards_original_roller_id", "original_roller_id"),)

    @property
    def current_card_id(self) -> int:
        """Return the active card ID (rerolled if available, else original)."""
        if self.rerolled and self.rerolled_card_id:
            return self.rerolled_card_id
        return self.original_card_id

    @property
    def card_id(self) -> int:
        """Backward-compatible alias for the active card id."""
        return self.current_card_id


class CharacterModel(Base):
    """Represents a custom character for a chat."""

    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    imageb64: Mapped[str] = mapped_column(Text, nullable=False)
    slot_iconb64: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_characters_chat_id", "chat_id"),)


class SpinsModel(Base):
    """Tracks spin balances per user per chat."""

    __tablename__ = "spins"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[str] = mapped_column(Text, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    refresh_timestamp: Mapped[str] = mapped_column(Text, nullable=False)


class MegaspinsModel(Base):
    """Tracks megaspin progress and availability per user per chat."""

    __tablename__ = "megaspins"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[str] = mapped_column(Text, primary_key=True)
    spins_until_megaspin: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    megaspin_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ThreadModel(Base):
    """Stores thread IDs for chats (for topic-based messaging)."""

    __tablename__ = "threads"

    chat_id: Mapped[str] = mapped_column(Text, primary_key=True)
    type: Mapped[str] = mapped_column(Text, primary_key=True, default="main")
    thread_id: Mapped[int] = mapped_column(Integer, nullable=False)


class SetModel(Base):
    """Represents a card set/season."""

    __tablename__ = "sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationship to cards (uses composite FK from cards table)
    cards: Mapped[List["CardModel"]] = relationship(
        "CardModel",
        back_populates="card_set",
        foreign_keys="[CardModel.set_id, CardModel.season_id]",
        primaryjoin="and_(SetModel.id == CardModel.set_id, SetModel.season_id == CardModel.season_id)",
    )


class MinesweeperGameModel(Base):
    """Represents a minesweeper game state."""

    __tablename__ = "minesweeper_games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chat_id: Mapped[str] = mapped_column(String, nullable=False)
    bet_card_id: Mapped[int] = mapped_column(Integer, nullable=False)
    bet_card_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bet_card_rarity: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mine_positions: Mapped[str] = mapped_column(String, nullable=False)  # JSON string
    claim_point_positions: Mapped[str] = mapped_column(String, nullable=False)  # JSON string
    revealed_cells: Mapped[str] = mapped_column(String, nullable=False, default="[]")  # JSON string
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    moves_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reward_card_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    last_updated_timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    source_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_minesweeper_user_chat", "user_id", "chat_id"),
        Index("idx_minesweeper_status", "status"),
        Index("idx_minesweeper_started", "started_timestamp"),
    )


class RideTheBusGameModel(Base):
    """Represents a Ride the Bus game state."""

    __tablename__ = "rtb_games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chat_id: Mapped[str] = mapped_column(String, nullable=False)
    bet_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    card_ids: Mapped[str] = mapped_column(String, nullable=False)  # JSON string
    card_rarities: Mapped[str] = mapped_column(String, nullable=False)  # JSON string
    card_titles: Mapped[str] = mapped_column(String, nullable=False)  # JSON string
    current_position: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_multiplier: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    started_timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    last_updated_timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_rtb_user_chat", "user_id", "chat_id"),
        Index("idx_rtb_status", "status"),
        Index("idx_rtb_started", "started_timestamp"),
    )


# Configure SQLite-specific settings via events
@event.listens_for(Base.metadata, "after_create")
def set_sqlite_pragma(target, connection, **kw):
    """Configure SQLite pragmas after table creation."""
    if connection.dialect.name == "sqlite":
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
