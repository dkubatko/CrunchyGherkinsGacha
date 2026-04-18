"""Pydantic schemas (DTOs) for API responses and data transfer.

These schemas are decoupled from the ORM models and provide a clean
interface for serialization, validation, and API responses.
"""

from __future__ import annotations

import base64
import datetime
import html
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class User(BaseModel):
    """User data transfer object."""

    user_id: int
    username: str
    display_name: Optional[str]
    profile_image_b64: Optional[str] = None
    slot_icon_b64: Optional[str] = None

    @classmethod
    def from_orm(cls, user_orm) -> "User":
        """Convert a UserModel ORM object to a User schema."""
        profile_image_b64 = (
            base64.b64encode(user_orm.profile_image).decode("utf-8")
            if user_orm.profile_image
            else None
        )
        slot_icon_b64 = (
            base64.b64encode(user_orm.slot_icon).decode("utf-8") if user_orm.slot_icon else None
        )
        return cls(
            user_id=user_orm.user_id,
            username=user_orm.username,
            display_name=user_orm.display_name,
            profile_image_b64=profile_image_b64,
            slot_icon_b64=slot_icon_b64,
        )


class Card(BaseModel):
    """Card data transfer object (without image data)."""

    id: int
    base_name: str
    modifier: Optional[str] = None
    rarity: str
    owner: Optional[str]
    user_id: Optional[int]
    file_id: Optional[str]
    chat_id: Optional[str]
    created_at: Optional[datetime.datetime] = None
    locked: bool = False
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    set_id: Optional[int] = None
    season_id: int = 0
    set_name: Optional[str] = None
    updated_at: Optional[datetime.datetime] = None
    description: Optional[str] = None
    aspect_count: int = 0
    equipped_aspects: List["CardAspect"] = []

    def title(self, include_id: bool = False, include_rarity: bool = False, include_emoji: bool = False) -> str:
        """Return the card's title, optionally including rarity and ID.

        Args:
            include_rarity: If True, includes rarity prefix. Default is False.
            include_id: If True, includes card ID in brackets as prefix. Default is False.
            include_emoji: If True, prepends 🃏 emoji. Default is False.

        Returns:
            HTML-escaped title text.
        """
        parts = []

        if include_emoji:
            parts.append("🃏")

        if include_id:
            parts.append(f"[{self.id}]")

        if include_rarity:
            parts.append(self.rarity.capitalize())

        if self.modifier:
            parts.append(self.modifier)
        parts.append(self.base_name)

        title_text = " ".join(parts).strip()
        return html.escape(title_text)

    @classmethod
    def from_orm(cls, card_orm) -> "Card":
        """Convert a CardModel ORM object to a Card schema."""
        set_name = card_orm.card_set.name if card_orm.card_set else ""

        equipped_aspects = (
            [CardAspect.from_orm(ca) for ca in card_orm.equipped_aspects]
            if card_orm.equipped_aspects
            else []
        )

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
            season_id=card_orm.season_id,
            set_name=set_name,
            updated_at=card_orm.updated_at,
            description=card_orm.description,
            aspect_count=card_orm.aspect_count,
            equipped_aspects=equipped_aspects,
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
        image_bytes = card_orm.image.image if card_orm.image else None
        image_b64 = base64.b64encode(image_bytes).decode("utf-8") if image_bytes else ""

        set_name = card_orm.card_set.name if card_orm.card_set else ""

        equipped_aspects = (
            [CardAspect.from_orm(ca) for ca in card_orm.equipped_aspects]
            if card_orm.equipped_aspects
            else []
        )

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
            season_id=card_orm.season_id,
            set_name=set_name,
            image_b64=image_b64,
            updated_at=card_orm.updated_at,
            description=card_orm.description,
            aspect_count=card_orm.aspect_count,
            equipped_aspects=equipped_aspects,
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


class Set(BaseModel):
    """Card set data transfer object."""

    id: int
    season_id: int
    name: str
    source: Optional[str] = None
    description: Optional[str] = None
    active: bool

    @classmethod
    def from_orm(cls, set_orm) -> "Set":
        """Convert a SetModel ORM object to a Set schema."""
        return cls(
            id=set_orm.id,
            season_id=set_orm.season_id,
            name=set_orm.name,
            source=set_orm.source,
            description=set_orm.description,
            active=set_orm.active,
        )


class RolledCard(BaseModel):
    """Rolled card state data transfer object."""

    roll_id: int
    original_card_id: int
    rerolled_card_id: Optional[int] = None
    created_at: Optional[datetime.datetime] = None
    original_roller_id: int
    rerolled: bool
    being_rerolled: bool
    attempted_by: Optional[str]
    is_locked: bool
    original_rarity: Optional[str] = None

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
            original_rarity=rolled_orm.original_rarity,
        )


class Character(BaseModel):
    """Character data transfer object."""

    id: int
    chat_id: str
    name: str
    image_b64: str
    slot_icon_b64: Optional[str] = None

    @classmethod
    def from_orm(cls, char_orm) -> "Character":
        """Convert a CharacterModel ORM object to a Character schema."""
        image_b64 = base64.b64encode(char_orm.image).decode("utf-8") if char_orm.image else ""
        slot_icon_b64 = (
            base64.b64encode(char_orm.slot_icon).decode("utf-8") if char_orm.slot_icon else None
        )
        return cls(
            id=char_orm.id,
            chat_id=char_orm.chat_id,
            name=char_orm.name,
            image_b64=image_b64,
            slot_icon_b64=slot_icon_b64,
        )


class Spins(BaseModel):
    """User spins data transfer object."""

    user_id: int
    chat_id: str
    count: int
    login_streak: int = 0
    last_bonus_date: Optional[datetime.date] = None

    @classmethod
    def from_orm(cls, spins_orm) -> "Spins":
        """Convert a SpinsModel ORM object to a Spins schema."""
        return cls(
            user_id=spins_orm.user_id,
            chat_id=spins_orm.chat_id,
            count=spins_orm.count,
            login_streak=spins_orm.login_streak,
            last_bonus_date=spins_orm.last_bonus_date,
        )


class Megaspins(BaseModel):
    """User megaspins progress data transfer object."""

    user_id: int
    chat_id: str
    spins_until_megaspin: int
    megaspin_available: bool

    @classmethod
    def from_orm(cls, megaspins_orm) -> "Megaspins":
        """Convert a MegaspinsModel ORM object to a Megaspins schema."""
        return cls(
            user_id=megaspins_orm.user_id,
            chat_id=megaspins_orm.chat_id,
            spins_until_megaspin=megaspins_orm.spins_until_megaspin,
            megaspin_available=megaspins_orm.megaspin_available,
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
        return cls(
            id=game_orm.id,
            user_id=game_orm.user_id,
            chat_id=game_orm.chat_id,
            bet_card_id=game_orm.bet_card_id,
            bet_card_title=game_orm.bet_card_title,
            bet_card_rarity=game_orm.bet_card_rarity,
            mine_positions=game_orm.mine_positions,
            claim_point_positions=game_orm.claim_point_positions,
            revealed_cells=game_orm.revealed_cells,
            status=game_orm.status,
            moves_count=game_orm.moves_count,
            reward_card_id=game_orm.reward_card_id,
            started_timestamp=game_orm.started_timestamp,
            last_updated_timestamp=game_orm.last_updated_timestamp,
            source_type=game_orm.source_type,
            source_id=game_orm.source_id,
        )


class RideTheBusGame(BaseModel):
    """Ride the Bus game state data transfer object."""

    id: int
    user_id: int
    chat_id: str
    bet_amount: int
    card_ids: List[int]
    card_rarities: List[str]
    card_titles: List[str]
    current_position: int  # 1-5, how many cards have been revealed
    current_multiplier: int  # x2 -> x3 -> x5 -> x10
    status: str  # 'active', 'won', 'lost', 'cashed_out'
    started_timestamp: datetime.datetime
    last_updated_timestamp: datetime.datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert game state to dictionary for API responses."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "bet_amount": self.bet_amount,
            "card_ids": self.card_ids,
            "card_rarities": self.card_rarities,
            "card_titles": self.card_titles,
            "current_position": self.current_position,
            "current_multiplier": self.current_multiplier,
            "status": self.status,
            "started_timestamp": self.started_timestamp.isoformat(),
            "last_updated_timestamp": self.last_updated_timestamp.isoformat(),
        }

    @classmethod
    def from_orm(cls, game_orm) -> "RideTheBusGame":
        """Convert a RideTheBusGameModel ORM object to a RideTheBusGame schema."""
        return cls(
            id=game_orm.id,
            user_id=game_orm.user_id,
            chat_id=game_orm.chat_id,
            bet_amount=game_orm.bet_amount,
            card_ids=game_orm.card_ids,
            card_rarities=game_orm.card_rarities,
            card_titles=game_orm.card_titles,
            current_position=game_orm.current_position,
            current_multiplier=game_orm.current_multiplier,
            status=game_orm.status,
            started_timestamp=game_orm.started_timestamp,
            last_updated_timestamp=game_orm.last_updated_timestamp,
        )


class Event(BaseModel):
    """Event data transfer object for telemetry."""

    id: int
    event_type: str
    outcome: str
    user_id: int
    chat_id: str
    card_id: Optional[int] = None
    aspect_id: Optional[int] = None
    timestamp: datetime.datetime
    payload: Optional[Dict[str, Any]] = None

    @classmethod
    def from_orm(cls, event_orm) -> "Event":
        """Convert an EventModel ORM object to an Event schema."""
        return cls(
            id=event_orm.id,
            event_type=event_orm.event_type,
            outcome=event_orm.outcome,
            user_id=event_orm.user_id,
            chat_id=event_orm.chat_id,
            card_id=event_orm.card_id,
            aspect_id=event_orm.aspect_id,
            timestamp=event_orm.timestamp,
            payload=event_orm.payload,
        )


class Achievement(BaseModel):
    """Achievement data transfer object."""

    id: int
    name: str
    description: str
    icon_b64: Optional[str] = None

    @classmethod
    def from_orm(cls, achievement_orm) -> "Achievement":
        """Convert an AchievementModel ORM object to an Achievement schema."""
        icon_b64 = (
            base64.b64encode(achievement_orm.icon).decode("utf-8") if achievement_orm.icon else None
        )
        return cls(
            id=achievement_orm.id,
            name=achievement_orm.name,
            description=achievement_orm.description,
            icon_b64=icon_b64,
        )


class UserAchievement(BaseModel):
    """User achievement data transfer object."""

    id: int
    user_id: int
    achievement_id: int
    unlocked_at: datetime.datetime
    achievement: Optional[Achievement] = None

    @classmethod
    def from_orm(cls, user_achievement_orm, include_achievement: bool = True) -> "UserAchievement":
        """Convert a UserAchievementModel ORM object to a UserAchievement schema."""
        achievement = None
        if include_achievement and user_achievement_orm.achievement:
            achievement = Achievement.from_orm(user_achievement_orm.achievement)

        return cls(
            id=user_achievement_orm.id,
            user_id=user_achievement_orm.user_id,
            achievement_id=user_achievement_orm.achievement_id,
            unlocked_at=user_achievement_orm.unlocked_at,
            achievement=achievement,
        )


# ---------------------------------------------------------------------------
# Aspect system schemas (Gacha 2.0)
# ---------------------------------------------------------------------------


class AspectType(BaseModel):
    """Aspect type (e.g., Location, Creature, Mood) data transfer object."""

    id: int
    name: str
    description: Optional[str] = None
    created_at: Optional[datetime.datetime] = None

    @classmethod
    def from_orm(cls, type_orm) -> "AspectType":
        """Convert an AspectTypeModel ORM object to an AspectType schema."""
        return cls(
            id=type_orm.id,
            name=type_orm.name,
            description=type_orm.description,
            created_at=type_orm.created_at,
        )


class AspectDefinition(BaseModel):
    """Aspect definition (catalog entry) data transfer object."""

    id: int
    name: str
    rarity: str
    season_id: int
    set_id: int
    set_name: Optional[str] = None
    set_description: Optional[str] = None
    source: str = "all"
    type_id: Optional[int] = None
    type_name: Optional[str] = None
    type_description: Optional[str] = None
    created_at: Optional[datetime.datetime] = None

    def title(self, include_id: bool = False, include_rarity: bool = False, include_emoji: bool = False) -> str:
        """Return ``[id] Rarity Name`` (HTML-escaped)."""
        parts: list[str] = []
        if include_emoji:
            parts.append("🔮")
        if include_id:
            parts.append(f"[{self.id}]")
        if include_rarity:
            parts.append(self.rarity.capitalize())
        parts.append(self.name)
        return html.escape(" ".join(parts))

    def context_label(self, include_descriptions: bool = True) -> str:
        """Build a rich label with type and set context for image generation prompts.

        Args:
            include_descriptions: If True, include descriptions after names.
                If False, only include names (for concise image reference labels).

        Returns e.g. '"Valhalla" (type: Location — a place, set: Fantasy — mythological worlds)'
        or just '"Valhalla"' if no set/type info is available.
        """
        label = f'"{self.name}"'
        context_parts = []
        if self.type_name:
            type_info = self.type_name
            if include_descriptions and self.type_description:
                type_info += f' — {self.type_description}'
            context_parts.append(f'type: {type_info}')
        if self.set_name:
            set_info = self.set_name
            if include_descriptions and self.set_description:
                set_info += f' — {self.set_description}'
            context_parts.append(f'set: {set_info}')
        if context_parts:
            label += f' ({", ".join(context_parts)})'
        return label

    @classmethod
    def from_orm(cls, aspect_def_orm) -> "AspectDefinition":
        """Convert an AspectDefinitionModel ORM object to an AspectDefinition schema."""
        asp_set = aspect_def_orm.aspect_set
        asp_type = aspect_def_orm.aspect_type
        return cls(
            id=aspect_def_orm.id,
            set_id=aspect_def_orm.set_id,
            season_id=aspect_def_orm.season_id,
            name=aspect_def_orm.name,
            rarity=aspect_def_orm.rarity,
            type_id=aspect_def_orm.type_id,
            type_name=asp_type.name if asp_type else None,
            type_description=asp_type.description if asp_type else None,
            created_at=aspect_def_orm.created_at,
            set_name=asp_set.name if asp_set else None,
            set_description=asp_set.description if asp_set else None,
            source=asp_set.source if asp_set else "all",
        )


class OwnedAspect(BaseModel):
    """Owned aspect instance data transfer object (without image data)."""

    id: int
    aspect_definition_id: Optional[int] = None
    name: Optional[str] = None
    owner: Optional[str] = None
    user_id: Optional[int] = None
    chat_id: str
    season_id: int
    rarity: str
    locked: bool = False
    file_id: Optional[str] = None
    created_at: Optional[datetime.datetime] = None
    display_name: str = ""
    aspect_definition: Optional[AspectDefinition] = None

    def title(self, include_id: bool = False, include_rarity: bool = False, include_emoji: bool = False) -> str:
        """Return ``[id] Rarity Name`` (HTML-escaped)."""
        parts: list[str] = []
        if include_emoji:
            parts.append("🔮")
        if include_id:
            parts.append(f"[{self.id}]")
        if include_rarity:
            parts.append(self.rarity.capitalize())
        parts.append(self.display_name)
        return html.escape(" ".join(parts))

    @classmethod
    def from_orm(cls, aspect_orm) -> "OwnedAspect":
        """Convert an OwnedAspectModel ORM object to an OwnedAspect schema."""
        # Resolve display name: custom override first, then definition name
        display_name = aspect_orm.name or ""
        aspect_def = None
        if aspect_orm.aspect_definition is not None:
            aspect_def = AspectDefinition.from_orm(aspect_orm.aspect_definition)
            if not display_name:
                display_name = aspect_orm.aspect_definition.name

        return cls(
            id=aspect_orm.id,
            aspect_definition_id=aspect_orm.aspect_definition_id,
            name=aspect_orm.name,
            owner=aspect_orm.owner,
            user_id=aspect_orm.user_id,
            chat_id=aspect_orm.chat_id,
            season_id=aspect_orm.season_id,
            rarity=aspect_orm.rarity,
            locked=aspect_orm.locked,
            file_id=aspect_orm.file_id,
            created_at=aspect_orm.created_at,
            display_name=display_name,
            aspect_definition=aspect_def,
        )


class OwnedAspectWithImage(OwnedAspect):
    """Owned aspect instance with base64-encoded sphere image data."""

    image_b64: str = ""
    thumbnail_b64: str = ""

    def get_media(self):
        """Return file_id if available, otherwise return decoded base64 image data."""
        if self.file_id:
            return self.file_id
        return base64.b64decode(self.image_b64)

    @classmethod
    def from_orm(cls, aspect_orm) -> "OwnedAspectWithImage":
        """Convert an OwnedAspectModel (with eager-loaded image) to schema."""
        image_bytes = aspect_orm.image.image if aspect_orm.image else None
        thumbnail_bytes = aspect_orm.image.thumbnail if aspect_orm.image else None
        image_b64 = base64.b64encode(image_bytes).decode("utf-8") if image_bytes else ""
        thumbnail_b64 = base64.b64encode(thumbnail_bytes).decode("utf-8") if thumbnail_bytes else ""

        # Resolve display name
        display_name = aspect_orm.name or ""
        aspect_def = None
        if aspect_orm.aspect_definition is not None:
            aspect_def = AspectDefinition.from_orm(aspect_orm.aspect_definition)
            if not display_name:
                display_name = aspect_orm.aspect_definition.name

        return cls(
            id=aspect_orm.id,
            aspect_definition_id=aspect_orm.aspect_definition_id,
            name=aspect_orm.name,
            owner=aspect_orm.owner,
            user_id=aspect_orm.user_id,
            chat_id=aspect_orm.chat_id,
            season_id=aspect_orm.season_id,
            rarity=aspect_orm.rarity,
            locked=aspect_orm.locked,
            file_id=aspect_orm.file_id,
            created_at=aspect_orm.created_at,
            display_name=display_name,
            aspect_definition=aspect_def,
            image_b64=image_b64,
            thumbnail_b64=thumbnail_b64,
        )


class CardAspect(BaseModel):
    """Junction record: an aspect equipped on a card."""

    id: int
    card_id: int
    aspect_id: int
    order: int
    equipped_at: Optional[datetime.datetime] = None
    aspect: Optional[OwnedAspect] = None

    @classmethod
    def from_orm(cls, ca_orm) -> "CardAspect":
        """Convert a CardAspectModel ORM object to a CardAspect schema."""
        aspect = None
        if ca_orm.aspect is not None:
            aspect = OwnedAspect.from_orm(ca_orm.aspect)

        return cls(
            id=ca_orm.id,
            card_id=ca_orm.card_id,
            aspect_id=ca_orm.aspect_id,
            order=ca_orm.order,
            equipped_at=ca_orm.equipped_at,
            aspect=aspect,
        )


class RolledAspect(BaseModel):
    """Rolled aspect state data transfer object."""

    roll_id: int
    original_aspect_id: int
    rerolled_aspect_id: Optional[int] = None
    created_at: Optional[datetime.datetime] = None
    original_roller_id: int
    rerolled: bool
    being_rerolled: bool
    attempted_by: Optional[str]
    is_locked: bool
    original_rarity: Optional[str] = None

    @property
    def current_aspect_id(self) -> int:
        """Get the current active aspect ID (rerolled if available, otherwise original)."""
        if self.rerolled and self.rerolled_aspect_id:
            return self.rerolled_aspect_id
        return self.original_aspect_id

    @property
    def aspect_id(self) -> int:
        """Backward-compatible alias for the active aspect id."""
        return self.current_aspect_id

    @classmethod
    def from_orm(cls, rolled_orm) -> "RolledAspect":
        """Convert a RolledAspectModel ORM object to a RolledAspect schema."""
        return cls(
            roll_id=rolled_orm.roll_id,
            original_aspect_id=rolled_orm.original_aspect_id,
            rerolled_aspect_id=rolled_orm.rerolled_aspect_id,
            created_at=rolled_orm.created_at,
            original_roller_id=rolled_orm.original_roller_id,
            rerolled=rolled_orm.rerolled,
            being_rerolled=rolled_orm.being_rerolled,
            attempted_by=rolled_orm.attempted_by,
            is_locked=rolled_orm.is_locked,
            original_rarity=rolled_orm.original_rarity,
        )


class AdminUser(BaseModel):
    """Admin user data transfer object (excludes sensitive fields)."""

    id: int
    username: str
    telegram_user_id: int

    @classmethod
    def from_orm(cls, admin_orm) -> "AdminUser":
        """Convert an AdminUserModel ORM object to an AdminUser schema."""
        return cls(
            id=admin_orm.id,
            username=admin_orm.username,
            telegram_user_id=admin_orm.telegram_user_id,
        )
