"""Unified roll manager for card and aspect rolls.

``RollManager`` replaces the legacy ``RolledCardManager`` and handles
both card-based and aspect-based rolls: caption generation, keyboard
construction, state queries, and claim/lock/reroll delegation.

Claim logic is fully delegated to the service layer (atomic
``card_service.try_claim_card`` / ``aspect_service.try_claim_aspect``),
so there is **no** multi-transaction race-condition window.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Literal, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from settings.constants import (
    # Card templates
    CARD_CAPTION_BASE,
    CARD_STATUS_UNCLAIMED,
    CARD_STATUS_CLAIMED,
    CARD_STATUS_LOCKED,
    CARD_STATUS_ATTEMPTED,
    CARD_STATUS_REROLLING,
    CARD_STATUS_REROLLED,
    CARD_STATUS_PRE_CLAIM_MESSAGES,
    # Aspect templates
    ASPECT_CAPTION_BASE,
    ASPECT_STATUS_UNCLAIMED,
    ASPECT_STATUS_CLAIMED,
    ASPECT_STATUS_LOCKED,
    ASPECT_STATUS_ATTEMPTED,
    ASPECT_STATUS_REROLLING,
    ASPECT_STATUS_REROLLED,
    ASPECT_STATUS_PRE_CLAIM_MESSAGES,
    get_claim_cost,
)
from utils.services import (
    card_service,
    claim_service,
    rolled_card_service,
    rolled_aspect_service,
    aspect_service,
)
from utils.schemas import CardWithImage, OwnedAspect, RolledCard, RolledAspect

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types for claim / lock operations
# ---------------------------------------------------------------------------


class ClaimStatus(Enum):
    SUCCESS = "success"
    ALREADY_CLAIMED = "already_claimed"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    ALREADY_OWNED_BY_USER = "already_owned_by_user"


@dataclass
class ClaimAttemptResult:
    status: ClaimStatus
    balance: Optional[int] = None
    cost: Optional[int] = None


@dataclass
class LockAttemptResult:
    success: bool
    cost: int
    remaining_balance: Optional[int] = None
    current_balance: Optional[int] = None


@dataclass
class RerollResult:
    """Result of executing a reroll through :meth:`RollManager.execute_reroll`."""

    new_item_id: int
    image_b64: str
    rarity: str
    old_item_id: int
    old_rarity: str
    event_kwargs: dict


# ---------------------------------------------------------------------------
# RollManager
# ---------------------------------------------------------------------------


class RollManager:
    """Manages rolled item state and generates captions & keyboards.

    Args:
        roll_type: ``"card"`` or ``"aspect"``.
        roll_id: The ``roll_id`` in the corresponding ``rolled_cards`` /
                 ``rolled_aspects`` table.
    """

    def __init__(self, roll_type: Literal["card", "aspect"], roll_id: int):
        self.roll_type = roll_type
        self.roll_id = roll_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_rolled(self) -> Optional[RolledCard | RolledAspect]:
        if self.roll_type == "card":
            return rolled_card_service.get_rolled_card_by_roll_id(self.roll_id)
        return rolled_aspect_service.get_rolled_aspect_by_roll_id(self.roll_id)

    def _get_item(self):
        """Return the active card or aspect schema, or None."""
        rolled = self._get_rolled()
        if rolled is None:
            return None
        if self.roll_type == "card":
            return card_service.get_card(rolled.current_card_id)
        return aspect_service.get_aspect_by_id(rolled.current_aspect_id)

    def _get_original_item(self):
        rolled = self._get_rolled()
        if rolled is None:
            return None
        if self.roll_type == "card":
            return card_service.get_card(rolled.original_card_id)
        return aspect_service.get_aspect_by_id(rolled.original_aspect_id)

    # Callback prefixes
    @property
    def _prefix_claim(self) -> str:
        return "claim" if self.roll_type == "card" else "aclaim"

    @property
    def _prefix_lock(self) -> str:
        return "lock" if self.roll_type == "card" else "alock"

    @property
    def _prefix_reroll(self) -> str:
        return "reroll" if self.roll_type == "card" else "areroll"

    # ------------------------------------------------------------------
    # Public state queries
    # ------------------------------------------------------------------

    @property
    def rolled(self):
        return self._get_rolled()

    @property
    def item(self):
        return self._get_item()

    @property
    def original_item(self):
        return self._get_original_item()

    @property
    def current_item_id(self) -> Optional[int]:
        rolled = self._get_rolled()
        if rolled is None:
            return None
        if self.roll_type == "card":
            return rolled.current_card_id
        return rolled.current_aspect_id

    def is_valid(self) -> bool:
        return self._get_rolled() is not None and self._get_item() is not None

    def is_claimed(self) -> bool:
        item = self._get_item()
        if item is None:
            return False
        return item.owner is not None

    def is_locked(self) -> bool:
        rolled = self._get_rolled()
        return rolled is not None and rolled.is_locked

    def is_being_rerolled(self) -> bool:
        rolled = self._get_rolled()
        return rolled is not None and rolled.being_rerolled

    def is_rerolled(self) -> bool:
        rolled = self._get_rolled()
        return rolled is not None and bool(rolled.rerolled)

    def is_reroll_expired(self) -> bool:
        if self.roll_type == "card":
            return rolled_card_service.is_rolled_card_reroll_expired(self.roll_id)
        return rolled_aspect_service.is_rolled_aspect_reroll_expired(self.roll_id)

    def can_user_reroll(self, user_id: int) -> bool:
        rolled = self._get_rolled()
        if not rolled:
            return False
        return (
            rolled.original_roller_id == user_id
            and not bool(rolled.rerolled)
            and not rolled.is_locked
            and not rolled.being_rerolled
            and not self.is_reroll_expired()
        )

    def can_user_lock(self, user_id: int, username: str) -> bool:
        item = self._get_item()
        if item is None or item.owner is None:
            return False
        return item.owner == username

    def get_attempted_users(self) -> List[str]:
        rolled = self._get_rolled()
        if not rolled or not rolled.attempted_by:
            return []
        return [u.strip() for u in rolled.attempted_by.split(",") if u.strip()]

    # ------------------------------------------------------------------
    # Claim (fully delegated to atomic service)
    # ------------------------------------------------------------------

    def claim_item(
        self,
        owner_username: str,
        user_id: Optional[int] = None,
        chat_id: Optional[str] = None,
    ) -> ClaimAttemptResult:
        """Attempt to claim the active item via the atomic service method.

        For cards: ``card_service.try_claim_card``
        For aspects: ``aspect_service.try_claim_aspect``

        Both perform row-locking + balance deduction + ownership
        assignment in a single transaction.
        """
        item = self._get_item()
        if item is None:
            raise ValueError("Rolled item has no active item to claim")

        claim_cost = get_claim_cost(item.rarity)

        # Pre-flight: check balance so we can report it to the user
        balance: Optional[int] = None
        if user_id is not None and chat_id is not None:
            balance = claim_service.get_claim_balance(user_id, chat_id)
            if balance < claim_cost:
                return ClaimAttemptResult(
                    ClaimStatus.INSUFFICIENT_BALANCE,
                    balance,
                    claim_cost,
                )

        if self.roll_type == "card":
            claimed = card_service.try_claim_card(
                item.id,
                owner_username,
                user_id,
                chat_id=chat_id,
                claim_cost=claim_cost,
            )
        else:
            claimed = aspect_service.try_claim_aspect(
                item.id,
                user_id,
                owner_username,
                chat_id,
            )

        if not claimed:
            # Check if user already owns it (double-click)
            refreshed = self._get_item()
            if refreshed and refreshed.owner == owner_username:
                return ClaimAttemptResult(
                    ClaimStatus.ALREADY_OWNED_BY_USER,
                    balance,
                    claim_cost,
                )

            if owner_username:
                self.add_claim_attempt(owner_username)
            return ClaimAttemptResult(
                ClaimStatus.ALREADY_CLAIMED,
                balance,
                claim_cost,
            )

        # Fetch updated balance after successful claim
        remaining_balance = balance
        if user_id is not None and chat_id is not None:
            remaining_balance = claim_service.get_claim_balance(user_id, chat_id)

        return ClaimAttemptResult(
            ClaimStatus.SUCCESS,
            remaining_balance,
            claim_cost,
        )

    # ------------------------------------------------------------------
    # Lock
    # ------------------------------------------------------------------

    def lock_item(
        self,
        user_id: int,
        chat_id: Optional[str],
    ) -> LockAttemptResult:
        """Lock the item, consuming claim points when required."""
        rolled = self._get_rolled()
        if rolled is None:
            raise ValueError("Rolled item state not found")

        item = self._get_item()
        if item is None:
            raise ValueError("Rolled item has no active item to lock")

        is_original_roller = rolled.original_roller_id == user_id
        cost = 0 if is_original_roller else get_claim_cost(item.rarity)

        remaining_balance: Optional[int] = None
        current_balance: Optional[int] = None

        if cost > 0:
            if user_id is None or chat_id is None:
                raise ValueError("User and chat IDs are required to lock with a cost")

            current_balance = claim_service.get_claim_balance(user_id, chat_id)
            if current_balance < cost:
                return LockAttemptResult(False, cost, None, current_balance)

            new_balance = claim_service.reduce_claim_points(user_id, chat_id, cost)
            if new_balance is None:
                return LockAttemptResult(False, cost, None, current_balance)

            remaining_balance = new_balance
            current_balance = new_balance

        self.set_locked(True)

        return LockAttemptResult(True, cost, remaining_balance, current_balance)

    # ------------------------------------------------------------------
    # State mutations
    # ------------------------------------------------------------------

    def set_being_rerolled(self, being_rerolled: bool) -> None:
        if self.roll_type == "card":
            rolled_card_service.set_rolled_card_being_rerolled(self.roll_id, being_rerolled)
        else:
            rolled_aspect_service.set_rolled_aspect_being_rerolled(self.roll_id, being_rerolled)

    def mark_rerolled(
        self,
        new_item_id: Optional[int] = None,
        original_rarity: Optional[str] = None,
    ) -> None:
        if self.roll_type == "card":
            rolled_card_service.set_rolled_card_rerolled(
                self.roll_id,
                new_item_id,
                original_rarity,
            )
        else:
            rolled_aspect_service.set_rolled_aspect_rerolled(
                self.roll_id,
                new_item_id,
                original_rarity,
            )

    def set_locked(self, is_locked: bool) -> None:
        if self.roll_type == "card":
            rolled_card_service.set_rolled_card_locked(self.roll_id, is_locked)
        else:
            rolled_aspect_service.set_rolled_aspect_locked(self.roll_id, is_locked)

    def add_claim_attempt(self, username: str) -> None:
        if self.roll_type == "card":
            rolled_card_service.update_rolled_card_attempted_by(self.roll_id, username)
        else:
            rolled_aspect_service.update_rolled_aspect_attempted_by(self.roll_id, username)

    # ------------------------------------------------------------------
    # Caption generation
    # ------------------------------------------------------------------

    def _card_base_caption(self, card: CardWithImage) -> str:
        return CARD_CAPTION_BASE.format(
            card_id=card.id,
            card_title=card.title(),
            rarity=card.rarity,
        )

    def _aspect_base_caption(self, aspect: OwnedAspect) -> str:
        return ASPECT_CAPTION_BASE.format(
            aspect_id=aspect.id,
            aspect_name=aspect.display_name,
            rarity=aspect.rarity,
            set_name=(
                aspect.aspect_definition.set_name
                if aspect.aspect_definition and aspect.aspect_definition.set_name
                else ""
            ).title(),
        )

    def _base_caption(self, item) -> str:
        if self.roll_type == "card":
            return self._card_base_caption(item)
        return self._aspect_base_caption(item)

    def _status_templates(self):
        """Return the correct set of status templates for the roll type."""
        if self.roll_type == "card":
            return (
                CARD_STATUS_UNCLAIMED,
                CARD_STATUS_CLAIMED,
                CARD_STATUS_LOCKED,
                CARD_STATUS_ATTEMPTED,
                CARD_STATUS_REROLLING,
                CARD_STATUS_REROLLED,
            )
        return (
            ASPECT_STATUS_UNCLAIMED,
            ASPECT_STATUS_CLAIMED,
            ASPECT_STATUS_LOCKED,
            ASPECT_STATUS_ATTEMPTED,
            ASPECT_STATUS_REROLLING,
            ASPECT_STATUS_REROLLED,
        )

    def generate_caption(self) -> str:
        """Generate the appropriate caption for the current roll state."""
        rolled = self._get_rolled()
        if rolled is None:
            return "Error: Roll data not found"

        item = self._get_item()
        if item is None:
            return "Error: Item data not found"

        (
            STATUS_UNCLAIMED,
            STATUS_CLAIMED,
            STATUS_LOCKED,
            STATUS_ATTEMPTED,
            STATUS_REROLLING,
            STATUS_REROLLED,
        ) = self._status_templates()

        base = self._base_caption(item)

        if rolled.being_rerolled:
            return base + STATUS_REROLLING

        owner = item.owner
        if owner:
            caption = base + STATUS_CLAIMED.format(username=owner)

            # Attempted users (excluding the owner)
            if rolled.attempted_by:
                attempted = [
                    f"@{u.strip()}"
                    for u in rolled.attempted_by.split(",")
                    if u.strip() and u.strip() != owner
                ]
                if attempted:
                    caption += STATUS_ATTEMPTED.format(users=", ".join(attempted))

            if rolled.is_locked:
                caption += STATUS_LOCKED

            if rolled.rerolled:
                original_rarity = rolled.original_rarity or "Unknown"
                caption += STATUS_REROLLED.format(
                    original_rarity=original_rarity,
                    downgraded_rarity=item.rarity,
                )
            return caption
        else:
            caption = base + STATUS_UNCLAIMED
            if rolled.rerolled:
                original_rarity = rolled.original_rarity or "Unknown"
                caption += STATUS_REROLLED.format(
                    original_rarity=original_rarity,
                    downgraded_rarity=item.rarity,
                )
            return caption

    def generate_pre_claim_caption(self, message: Optional[str] = None) -> str:
        """Generate caption with a rotating status message during countdown."""
        messages_list = (
            CARD_STATUS_PRE_CLAIM_MESSAGES
            if self.roll_type == "card"
            else ASPECT_STATUS_PRE_CLAIM_MESSAGES
        )

        rolled = self._get_rolled()
        if rolled is None:
            return "Error: Roll data not found"

        item = self._get_item()
        if item is None:
            return "Error: Item data not found"

        base = self._base_caption(item)

        # Append rerolled info if applicable
        if rolled.rerolled:
            original_rarity = rolled.original_rarity or "Unknown"
            _, _, _, _, _, STATUS_REROLLED = self._status_templates()
            base += STATUS_REROLLED.format(
                original_rarity=original_rarity,
                downgraded_rarity=item.rarity,
            )

        status_message = message if message else messages_list[0]
        return base + f"\n\n<i>{status_message}</i>"

    # ------------------------------------------------------------------
    # Keyboard generation
    # ------------------------------------------------------------------

    def generate_keyboard(self) -> Optional[InlineKeyboardMarkup]:
        """Generate the appropriate inline keyboard for the current state."""
        rolled = self._get_rolled()
        if rolled is None:
            return None

        item = self._get_item()
        if item is None:
            return None

        if rolled.being_rerolled:
            return None

        keyboard = []

        if item.owner:
            # Claimed — show Lock and Reroll if eligible
            if not rolled.is_locked and not rolled.rerolled:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            "Lock", callback_data=f"{self._prefix_lock}_{self.roll_id}"
                        )
                    ]
                )
            if not rolled.is_locked and not rolled.rerolled and not self.is_reroll_expired():
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            "Reroll", callback_data=f"{self._prefix_reroll}_{self.roll_id}"
                        )
                    ]
                )
        else:
            # Unclaimed — show Claim button
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "Claim", callback_data=f"{self._prefix_claim}_{self.roll_id}"
                    )
                ]
            )

        return InlineKeyboardMarkup(keyboard) if keyboard else None

    # ------------------------------------------------------------------
    # Reroll execution
    # ------------------------------------------------------------------

    def execute_reroll(
        self,
        gemini_util,
        chat_id: str,
        downgraded_rarity: str,
        original_rarity: str,
        max_retries: int = 0,
        source: Optional[str] = None,
    ) -> "RerollResult":
        """Generate a replacement item, delete the old one, and update state.

        For card rolls: generates a new base card, adds it to the DB,
        deletes the old card, and marks the roll as rerolled.

        For aspect rolls: generates a new aspect (which is created in the
        DB by ``generate_aspect_for_chat``), deletes the old aspect, and
        marks the roll as rerolled.

        Returns a :class:`RerollResult` with the new item details and
        pre-built ``event_kwargs`` for the caller to log.
        """
        from utils import rolling

        active_item = self._get_item()
        if active_item is None:
            raise ValueError("No active item to reroll")

        old_item_id = active_item.id

        if self.roll_type == "card":
            generated = rolling.generate_base_card(
                gemini_util,
                downgraded_rarity,
                max_retries,
                chat_id=chat_id,
            )
            new_item_id = card_service.add_card_from_generated(generated, chat_id)
            card_service.delete_card(old_item_id)
            self.mark_rerolled(new_item_id, original_rarity)

            return RerollResult(
                new_item_id=new_item_id,
                image_b64=generated.image_b64,
                rarity=downgraded_rarity,
                old_item_id=old_item_id,
                old_rarity=original_rarity,
                event_kwargs={
                    "card_id": new_item_id,
                    "old_card_id": old_item_id,
                    "type": "base_card",
                    "modifier": generated.modifier,
                    "source_name": generated.base_name,
                    "source_type": generated.source_type,
                    "source_id": generated.source_id,
                },
            )
        else:
            generated = rolling.generate_aspect_for_chat(
                chat_id,
                gemini_util,
                downgraded_rarity,
                max_retries,
                source=source,
            )
            aspect_service.delete_aspect(old_item_id)
            self.mark_rerolled(generated.aspect_id, original_rarity)

            return RerollResult(
                new_item_id=generated.aspect_id,
                image_b64=generated.image_b64,
                rarity=downgraded_rarity,
                old_item_id=old_item_id,
                old_rarity=original_rarity,
                event_kwargs={
                    "aspect_id": generated.aspect_id,
                    "old_aspect_id": old_item_id,
                    "type": "aspect",
                    "aspect_name": generated.aspect_name,
                    "aspect_definition_id": generated.aspect_definition_id,
                },
            )

    @property
    def pre_claim_messages(self) -> list[str]:
        if self.roll_type == "card":
            return CARD_STATUS_PRE_CLAIM_MESSAGES
        return ASPECT_STATUS_PRE_CLAIM_MESSAGES
