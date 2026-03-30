"""SQLAlchemy ORM models for the gacha bot database.

This module defines all database tables using SQLAlchemy declarative ORM.
Each model corresponds to a table in the PostgreSQL database.
"""

from __future__ import annotations

import datetime
import html
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:
    pass


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class CardModel(Base):
    """Represents a gacha card in the database."""

    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    base_name: Mapped[str] = mapped_column(Text, nullable=False)
    modifier: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, doc="Display name prefix (user-chosen). NULL for base cards."
    )
    rarity: Mapped[str] = mapped_column(Text, nullable=False)
    aspect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    owner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    file_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chat_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    set_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    season_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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

    # Relationship to equipped aspects (ordered junction table)
    equipped_aspects: Mapped[List["CardAspectModel"]] = relationship(
        "CardAspectModel",
        back_populates="card",
        cascade="all, delete-orphan",
        order_by="CardAspectModel.order",
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

        if self.modifier:
            parts.append(self.modifier)
        parts.append(self.base_name)

        title_text = " ".join(parts).strip()
        return html.escape(title_text)


class CardImageModel(Base):
    """Stores card image data separately for performance."""

    __tablename__ = "card_images"

    card_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cards.id", ondelete="CASCADE"), primary_key=True
    )
    image: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    thumbnail: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    image_updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationship back to card
    card: Mapped["CardModel"] = relationship("CardModel", back_populates="image")

    __table_args__ = (Index("idx_card_images_card_id", "card_id"),)


class UserModel(Base):
    """Represents a Telegram user registered with the bot."""

    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    profile_image: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    slot_icon: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

    # Relationship to chat memberships
    chat_memberships: Mapped[List["ChatModel"]] = relationship(
        "ChatModel", back_populates="user", cascade="all, delete-orphan"
    )


class ChatModel(Base):
    """Represents a user's membership in a chat (many-to-many relationship)."""

    __tablename__ = "chats"

    chat_id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), primary_key=True)

    # Relationship to user
    user: Mapped["UserModel"] = relationship("UserModel", back_populates="chat_memberships")


class ClaimModel(Base):
    """Tracks claim point balances per user per chat."""

    __tablename__ = "claims"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[str] = mapped_column(Text, primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class UserRollModel(Base):
    """Tracks when users last rolled in each chat."""

    __tablename__ = "user_rolls"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[str] = mapped_column(Text, primary_key=True)
    last_roll_timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class RolledCardModel(Base):
    """Tracks the state of rolled cards (for reroll mechanics)."""

    __tablename__ = "rolled_cards"

    roll_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    original_card_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    rerolled_card_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    original_roller_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    image: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    slot_icon: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

    __table_args__ = (Index("ix_characters_chat_id", "chat_id"),)


class SpinsModel(Base):
    """Tracks spin balances per user per chat."""

    __tablename__ = "spins"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[str] = mapped_column(Text, primary_key=True)
    count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    login_streak: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_bonus_date: Mapped[Optional[datetime.date]] = mapped_column(nullable=True)


class MegaspinsModel(Base):
    """Tracks megaspin progress and availability per user per chat."""

    __tablename__ = "megaspins"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[str] = mapped_column(Text, primary_key=True)
    spins_until_megaspin: Mapped[int] = mapped_column(BigInteger, nullable=False, default=100)
    megaspin_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ThreadModel(Base):
    """Stores thread IDs for chats (for topic-based messaging)."""

    __tablename__ = "threads"

    chat_id: Mapped[str] = mapped_column(Text, primary_key=True)
    type: Mapped[str] = mapped_column(Text, primary_key=True, default="main")
    thread_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class SetModel(Base):
    """Represents a card set/season."""

    __tablename__ = "sets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    season_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=0)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="all")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationship to cards (uses composite FK from cards table)
    cards: Mapped[List["CardModel"]] = relationship(
        "CardModel",
        back_populates="card_set",
        foreign_keys="[CardModel.set_id, CardModel.season_id]",
        primaryjoin="and_(SetModel.id == CardModel.set_id, SetModel.season_id == CardModel.season_id)",
    )

    # Relationship to slot icon (separate table to avoid overhead on set queries)
    icon: Mapped[Optional["SetIconModel"]] = relationship(
        "SetIconModel",
        back_populates="aspect_set",
        uselist=False,
        lazy="noload",
    )


class SetIconModel(Base):
    """Stores slot machine icon for an aspect set, separate from the main sets
    table to avoid overhead on large queries."""

    __tablename__ = "set_icons"

    set_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    season_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=0)
    icon: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    aspect_set: Mapped[Optional["SetModel"]] = relationship(
        "SetModel", back_populates="icon"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["set_id", "season_id"],
            ["sets.id", "sets.season_id"],
            name="fk_set_icons_set_season",
        ),
    )


class MinesweeperGameModel(Base):
    """Represents a minesweeper game state."""

    __tablename__ = "minesweeper_games"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[str] = mapped_column(String, nullable=False)
    bet_card_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bet_card_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bet_card_rarity: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mine_positions: Mapped[list] = mapped_column(JSONB, nullable=False)
    claim_point_positions: Mapped[list] = mapped_column(JSONB, nullable=False)
    revealed_cells: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    moves_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reward_card_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    started_timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_updated_timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (
        Index("idx_minesweeper_user_chat", "user_id", "chat_id"),
        Index("idx_minesweeper_status", "status"),
        Index("idx_minesweeper_started", "started_timestamp"),
    )


class RideTheBusGameModel(Base):
    """Represents a Ride the Bus game state."""

    __tablename__ = "rtb_games"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[str] = mapped_column(String, nullable=False)
    bet_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    card_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    card_rarities: Mapped[list] = mapped_column(JSONB, nullable=False)
    card_titles: Mapped[list] = mapped_column(JSONB, nullable=False)
    current_position: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    current_multiplier: Mapped[int] = mapped_column(BigInteger, nullable=False, default=2)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    started_timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_updated_timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("idx_rtb_user_chat", "user_id", "chat_id"),
        Index("idx_rtb_status", "status"),
        Index("idx_rtb_started", "started_timestamp"),
    )


class EventModel(Base):
    """Represents a telemetry event for logging and analytics."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[str] = mapped_column(Text, nullable=False)
    card_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    aspect_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_events_type_outcome", "event_type", "outcome"),
        Index("idx_events_user_timestamp", "user_id", "timestamp"),
        Index("idx_events_chat_timestamp", "chat_id", "timestamp"),
        Index("idx_events_card_id", "card_id"),
        Index("idx_events_aspect_id", "aspect_id"),
    )


# ---------------------------------------------------------------------------
# Aspect system models (Gacha 2.0)
# ---------------------------------------------------------------------------


class AspectDefinitionModel(Base):
    """Catalog of aspect keywords grouped by set and rarity.

    Replaces the legacy modifier catalog for all new aspect-related code.
    Each row defines a named aspect (e.g., "Rainy" in the "Weather" set)
    that can be rolled and equipped onto cards.
    """

    __tablename__ = "aspect_definitions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    set_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    season_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    rarity: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationship to set (composite FK: set_id + season_id)
    aspect_set: Mapped[Optional["SetModel"]] = relationship(
        "SetModel",
        foreign_keys="[AspectDefinitionModel.set_id, AspectDefinitionModel.season_id]",
        primaryjoin="and_(AspectDefinitionModel.set_id == SetModel.id, AspectDefinitionModel.season_id == SetModel.season_id)",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["set_id", "season_id"],
            ["sets.id", "sets.season_id"],
            name="fk_aspect_definitions_set_season",
        ),
        Index("idx_aspect_definitions_set_season", "set_id", "season_id"),
        Index("idx_aspect_definitions_rarity", "rarity"),
        Index("idx_aspect_definitions_name", "name"),
    )


class OwnedAspectModel(Base):
    """A specific aspect instance owned (or pending claim) by a user.

    Each row is a unique instance with its own generated sphere image.
    ``owner``/``user_id`` are nullable because freshly-rolled aspects
    are unclaimed until someone uses ``/claim``.
    """

    __tablename__ = "owned_aspects"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aspect_definition_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("aspect_definitions.id"), nullable=True
    )
    name: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, doc="Custom name override for Unique/user-created aspects."
    )
    owner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    chat_id: Mapped[str] = mapped_column(Text, nullable=False)
    season_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rarity: Mapped[str] = mapped_column(Text, nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    file_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    aspect_definition: Mapped[Optional["AspectDefinitionModel"]] = relationship(
        "AspectDefinitionModel"
    )
    image: Mapped[Optional["AspectImageModel"]] = relationship(
        "AspectImageModel",
        back_populates="aspect",
        uselist=False,
        cascade="all, delete-orphan",
    )
    card_aspect_links: Mapped[List["CardAspectModel"]] = relationship("CardAspectModel")

    __table_args__ = (
        Index("idx_owned_aspects_chat_season", "chat_id", "season_id"),
        Index("idx_owned_aspects_user_season", "user_id", "season_id"),
        Index("idx_owned_aspects_owner_season", "owner", "season_id"),
        Index("idx_owned_aspects_rarity_season", "rarity", "season_id"),
        Index("idx_owned_aspects_file_id", "file_id"),
        Index("idx_owned_aspects_definition_id", "aspect_definition_id"),
    )

    @property
    def display_name(self) -> str:
        """Resolve the display name: custom override first, then definition name."""
        if self.name:
            return self.name
        if self.aspect_definition:
            return self.aspect_definition.name
        return ""


class AspectImageModel(Base):
    """Stores aspect sphere image data separately for performance.

    Mirrors the ``CardImageModel`` pattern — PK is also FK to ``owned_aspects``.
    """

    __tablename__ = "aspect_images"

    aspect_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("owned_aspects.id", ondelete="CASCADE"), primary_key=True
    )
    image: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    thumbnail: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    image_updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationship back to owned aspect
    aspect: Mapped["OwnedAspectModel"] = relationship("OwnedAspectModel", back_populates="image")

    __table_args__ = (Index("idx_aspect_images_aspect_id", "aspect_id"),)


class CardAspectModel(Base):
    """Junction table tracking which aspects are equipped on which cards.

    This is the sole source of truth for card-aspect equipment state.
    ``order`` is assigned chronologically (1–5) at equip time and is
    immutable after assignment.
    """

    __tablename__ = "card_aspects"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cards.id"), nullable=False)
    aspect_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("owned_aspects.id"), nullable=False
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    equipped_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    card: Mapped["CardModel"] = relationship("CardModel", back_populates="equipped_aspects")
    aspect: Mapped["OwnedAspectModel"] = relationship(
        "OwnedAspectModel", overlaps="card_aspect_links"
    )

    __table_args__ = (
        UniqueConstraint("aspect_id", name="uq_card_aspects_aspect_id"),
        UniqueConstraint("card_id", "order", name="uq_card_aspects_card_order"),
        CheckConstraint('"order" BETWEEN 1 AND 5', name="ck_card_aspects_order_range"),
        Index("idx_card_aspects_card_id_order", "card_id", "order"),
    )


class RolledAspectModel(Base):
    """Tracks the state of rolled aspects (for claim/reroll mechanics).

    Mirrors ``RolledCardModel`` but for aspect rolls. No FK constraints
    on aspect IDs — uses soft linking like rolled cards.
    """

    __tablename__ = "rolled_aspects"

    roll_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    original_aspect_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    rerolled_aspect_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    original_roller_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rerolled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    being_rerolled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempted_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    original_rarity: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_rolled_aspects_original_roller_id", "original_roller_id"),)

    @property
    def current_aspect_id(self) -> int:
        """Return the active aspect ID (rerolled if available, else original)."""
        if self.rerolled and self.rerolled_aspect_id:
            return self.rerolled_aspect_id
        return self.original_aspect_id

    @property
    def aspect_id(self) -> int:
        """Backward-compatible alias for the active aspect id."""
        return self.current_aspect_id


class AchievementModel(Base):
    """Represents an achievement definition."""

    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

    # Relationship to user achievements
    user_achievements: Mapped[List["UserAchievementModel"]] = relationship(
        "UserAchievementModel", back_populates="achievement", cascade="all, delete-orphan"
    )


class UserAchievementModel(Base):
    """Tracks which users have earned which achievements."""

    __tablename__ = "user_achievements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    achievement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False
    )
    unlocked_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationship to achievement
    achievement: Mapped["AchievementModel"] = relationship(
        "AchievementModel", back_populates="user_achievements"
    )

    __table_args__ = (
        Index("idx_user_achievements_user_id", "user_id"),
        Index("idx_user_achievements_achievement_id", "achievement_id"),
    )


class AspectCountModel(Base):
    """Tracks aspect-definition frequency per chat per season."""

    __tablename__ = "aspect_counts"

    chat_id: Mapped[str] = mapped_column(Text, primary_key=True)
    season_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    definition_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("aspect_definitions.id"), nullable=True
    )
    count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        Index("idx_aspect_counts_chat_season", "chat_id", "season_id"),
        Index("idx_aspect_counts_definition_id", "definition_id"),
    )


class AdminUserModel(Base):
    """Admin user for the modifier management dashboard.

    Stores credentials for the standalone admin dashboard.  Authentication
    uses bcrypt-hashed passwords with a Telegram-delivered OTP as 2FA.
    """

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    otp_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    otp_expires_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("idx_admin_users_username", "username"),)


class EquipSessionModel(Base):
    """Stores pending equip session data.

    Used by both the /equip chat command and the miniapp equip-initiate API
    to persist session state across the confirmation flow.  One pending
    equip per user per chat (unique on user_id + chat_id).
    """

    __tablename__ = "equip_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[str] = mapped_column(Text, nullable=False)
    aspect_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    card_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    aspect_name: Mapped[str] = mapped_column(Text, nullable=False)
    aspect_rarity: Mapped[str] = mapped_column(Text, nullable=False)
    card_title: Mapped[str] = mapped_column(Text, nullable=False)
    new_title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "chat_id", name="uq_equip_sessions_user_chat"),
        Index("idx_equip_sessions_user_chat", "user_id", "chat_id"),
    )
