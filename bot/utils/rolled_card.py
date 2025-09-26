"""RolledCard class for managing rolled card state and UI generation."""

import os
from typing import Optional, Tuple, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from settings.constants import (
    CARD_CAPTION_BASE,
    CARD_STATUS_UNCLAIMED,
    CARD_STATUS_CLAIMED,
    CARD_STATUS_LOCKED,
    CARD_STATUS_ATTEMPTED,
    CARD_STATUS_REROLLING,
    CARD_STATUS_REROLLED,
)
from utils import database


class RolledCardManager:
    """Manages rolled card state and generates captions and keyboards."""

    def __init__(self, card_id: int):
        self.card_id = card_id
        self._card: Optional[database.CardWithImage] = None
        self._rolled_card: Optional[database.RolledCard] = None

    @property
    def card(self) -> Optional[database.CardWithImage]:
        """Get the card data, loading it if necessary."""
        if self._card is None:
            self._card = database.get_card(self.card_id)
        return self._card

    @property
    def rolled_card(self) -> Optional[database.RolledCard]:
        """Get the rolled card state, loading it if necessary."""
        if self._rolled_card is None:
            self._rolled_card = database.get_rolled_card(self.card_id)
        return self._rolled_card

    def refresh(self) -> None:
        """Refresh cached data from database."""
        self._card = None
        self._rolled_card = None

    def is_valid(self) -> bool:
        """Check if both card and rolled_card data exist."""
        return self.card is not None and self.rolled_card is not None

    def is_claimed(self) -> bool:
        """Check if the card is claimed."""
        return self.card is not None and self.card.owner is not None

    def is_locked(self) -> bool:
        """Check if the card is locked from rerolling."""
        return self.rolled_card is not None and self.rolled_card.is_locked

    def is_being_rerolled(self) -> bool:
        """Check if the card is currently being rerolled."""
        return self.rolled_card is not None and self.rolled_card.being_rerolled

    def is_rerolled(self) -> bool:
        """Check if the card has been rerolled, safely handling None."""
        return self.rolled_card is not None and bool(self.rolled_card.rerolled)

    def is_reroll_expired(self) -> bool:
        """Check if the reroll time limit has expired."""
        return database.is_rolled_card_reroll_expired(self.card_id)

    def can_user_reroll(self, user_id: int) -> bool:
        """Check if a user can reroll this card."""
        if not self.rolled_card:
            return False
        return (
            self.rolled_card.original_roller_id == user_id
            and not self.is_rerolled()  # Can only reroll once
            and not self.is_locked()
            and not self.is_being_rerolled()
            and not self.is_reroll_expired()
        )

    def can_user_lock(self, user_id: int, username: str) -> bool:
        """Check if a user can lock this card."""
        if not self.is_claimed():
            return False
        return self.card.owner == username

    def get_attempted_users(self) -> List[str]:
        """Get list of users who attempted to claim this card."""
        if not self.rolled_card or not self.rolled_card.attempted_by:
            return []
        return [u.strip() for u in self.rolled_card.attempted_by.split(",") if u.strip()]

    def generate_caption(self) -> str:
        """Generate the appropriate caption for this rolled card."""
        if not self.is_valid():
            return "Error: Card data not found"

        card = self.card
        rolled_card = self.rolled_card

        card_title = f"{card.modifier} {card.base_name}"
        base_caption = CARD_CAPTION_BASE.format(
            card_id=self.card_id, card_title=card_title, rarity=card.rarity
        )

        if self.is_being_rerolled():
            return base_caption + CARD_STATUS_REROLLING

        if self.is_claimed():
            caption = base_caption + CARD_STATUS_CLAIMED.format(username=card.owner)

            # Add attempted users (excluding the owner)
            attempted_users = [u for u in self.get_attempted_users() if u != card.owner]
            if attempted_users:
                attempted_display = ", ".join([f"@{u}" for u in attempted_users])
                caption += CARD_STATUS_ATTEMPTED.format(users=attempted_display)

            if self.is_locked():
                caption += CARD_STATUS_LOCKED

            return caption
        else:
            caption = base_caption + CARD_STATUS_UNCLAIMED

            if self.is_rerolled():
                # This was rerolled from a higher rarity - show the original rarity
                original_rarity = rolled_card.original_rarity or "Unknown"
                caption += CARD_STATUS_REROLLED.format(
                    original_rarity=original_rarity,
                    downgraded_rarity=card.rarity,
                )

            return caption

    def generate_keyboard(self) -> Optional[InlineKeyboardMarkup]:
        """Generate the appropriate keyboard for this rolled card."""
        if not self.is_valid():
            return None

        rolled_card = self.rolled_card

        if self.is_being_rerolled():
            return None  # No buttons while rerolling

        keyboard = []

        if self.is_claimed():
            # Card is claimed - show Lock button if not already locked and not already rerolled
            if not self.is_locked() and not self.is_rerolled():
                keyboard.append(
                    [InlineKeyboardButton("Lock", callback_data=f"lock_{self.card_id}")]
                )
        else:
            # Card is unclaimed - show Claim button
            keyboard.append([InlineKeyboardButton("Claim", callback_data=f"claim_{self.card_id}")])

        # Add reroll button for both claimed and unclaimed cards (if conditions are met)
        if not self.is_reroll_expired() and not self.is_locked() and not self.is_rerolled():
            keyboard.append(
                [InlineKeyboardButton("Reroll", callback_data=f"reroll_{self.card_id}")]
            )

        return InlineKeyboardMarkup(keyboard) if keyboard else None

    def set_being_rerolled(self, being_rerolled: bool) -> None:
        """Set the being_rerolled status and refresh cache."""
        database.set_rolled_card_being_rerolled(self.card_id, being_rerolled)
        self.refresh()

    def mark_rerolled(self) -> None:
        """Mark the card as having been rerolled and refresh cache."""
        database.set_rolled_card_rerolled(self.card_id)
        self.refresh()

    def mark_rerolled_with_original_rarity(self, original_rarity: str) -> None:
        """Mark the card as having been rerolled with original rarity and refresh cache."""
        database.set_rolled_card_rerolled_with_original_rarity(self.card_id, original_rarity)
        self.refresh()

    def set_locked(self, is_locked: bool) -> None:
        """Set the locked status and refresh cache."""
        database.set_rolled_card_locked(self.card_id, is_locked)
        self.refresh()

    def add_claim_attempt(self, username: str) -> None:
        """Add a user to the attempted_by list and refresh cache."""
        database.update_rolled_card_attempted_by(self.card_id, username)
        self.refresh()
