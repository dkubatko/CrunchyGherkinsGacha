"""RolledCard class for managing rolled card state and UI generation."""

from typing import Optional, List
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

    def __init__(self, roll_id: int):
        self.roll_id = roll_id

    @property
    def rolled_card(self) -> Optional[database.RolledCard]:
        """Get the rolled card state, loading it if necessary."""
        return database.get_rolled_card_by_roll_id(self.roll_id)

    @property
    def current_card_id(self) -> Optional[int]:
        rolled_card = self.rolled_card
        if not rolled_card:
            return None
        return rolled_card.current_card_id

    @property
    def card(self) -> Optional[database.CardWithImage]:
        """Get the active card data, loading it if necessary."""
        rolled_card = self.rolled_card
        if not rolled_card:
            return None
        return database.get_card(rolled_card.current_card_id)

    @property
    def original_card(self) -> Optional[database.CardWithImage]:
        rolled_card = self.rolled_card
        if not rolled_card:
            return None
        return database.get_card(rolled_card.original_card_id)

    def is_valid(self) -> bool:
        """Check if both card and rolled_card data exist."""
        rolled_card = self.rolled_card
        if rolled_card is None:
            return False
        return database.get_card(rolled_card.current_card_id) is not None

    def is_claimed(self) -> bool:
        """Check if the card is claimed."""
        card = self.card
        return card is not None and card.owner is not None

    def is_locked(self) -> bool:
        """Check if the card is locked from rerolling."""
        rolled_card = self.rolled_card
        return rolled_card is not None and rolled_card.is_locked

    def is_being_rerolled(self) -> bool:
        """Check if the card is currently being rerolled."""
        rolled_card = self.rolled_card
        return rolled_card is not None and rolled_card.being_rerolled

    def is_rerolled(self) -> bool:
        """Check if the card has been rerolled, safely handling None."""
        rolled_card = self.rolled_card
        return rolled_card is not None and bool(rolled_card.rerolled)

    def is_reroll_expired(self) -> bool:
        """Check if the reroll time limit has expired."""
        return database.is_rolled_card_reroll_expired(self.roll_id)

    def claim(
        self,
        owner_username: str,
        user_id: Optional[int] = None,
        chat_id: Optional[str] = None,
    ) -> database.ClaimAttemptResult:
        """Attempt to claim the active card and track unsuccessful attempts."""
        card = self.card
        if card is None:
            raise ValueError("Rolled card has no active card to claim")

        result = database.claim_card(card.id, owner_username, user_id, chat_id)

        if result.status is database.ClaimStatus.ALREADY_CLAIMED and owner_username:
            database.update_rolled_card_attempted_by(self.roll_id, owner_username)

        return result

    def can_user_reroll(self, user_id: int) -> bool:
        """Check if a user can reroll this card."""
        rolled_card = self.rolled_card
        if not rolled_card:
            return False
        return (
            rolled_card.original_roller_id == user_id
            and not bool(rolled_card.rerolled)  # Can only reroll once
            and not rolled_card.is_locked
            and not rolled_card.being_rerolled
            and not self.is_reroll_expired()
        )

    def can_user_lock(self, user_id: int, username: str) -> bool:
        """Check if a user can lock this card."""
        card = self.card
        if card is None or card.owner is None:
            return False
        return card.owner == username

    def get_attempted_users(self) -> List[str]:
        """Get list of users who attempted to claim this card."""
        rolled_card = self.rolled_card
        if not rolled_card or not rolled_card.attempted_by:
            return []
        return [u.strip() for u in rolled_card.attempted_by.split(",") if u.strip()]

    def generate_caption(self) -> str:
        """Generate the appropriate caption for this rolled card."""
        rolled_card = self.rolled_card
        if rolled_card is None:
            return "Error: Card data not found"

        card = database.get_card(rolled_card.current_card_id)
        if card is None:
            return "Error: Card data not found"

        card_title = f"{card.modifier} {card.base_name}"
        base_caption = CARD_CAPTION_BASE.format(
            card_id=card.id, card_title=card_title, rarity=card.rarity
        )

        if rolled_card.being_rerolled:
            return base_caption + CARD_STATUS_REROLLING

        if card.owner:
            caption = base_caption + CARD_STATUS_CLAIMED.format(username=card.owner)

            # Add attempted users (excluding the owner)
            attempted_users: List[str] = []
            if rolled_card.attempted_by:
                for raw_username in rolled_card.attempted_by.split(","):
                    username = raw_username.strip()
                    if not username or username == card.owner:
                        continue
                    attempted_users.append(f"@{username}")
            if attempted_users:
                attempted_display = ", ".join(attempted_users)
                caption += CARD_STATUS_ATTEMPTED.format(users=attempted_display)

            if rolled_card.is_locked:
                caption += CARD_STATUS_LOCKED

            return caption
        else:
            caption = base_caption + CARD_STATUS_UNCLAIMED

            if rolled_card.rerolled:
                # This was rerolled from a higher rarity - show the original rarity
                original_card = database.get_card(rolled_card.original_card_id)
                original_rarity = original_card.rarity if original_card else "Unknown"
                caption += CARD_STATUS_REROLLED.format(
                    original_rarity=original_rarity,
                    downgraded_rarity=card.rarity,
                )

            return caption

    def generate_keyboard(self) -> Optional[InlineKeyboardMarkup]:
        """Generate the appropriate keyboard for this rolled card."""
        rolled_card = self.rolled_card
        if rolled_card is None:
            return None

        card = database.get_card(rolled_card.current_card_id)
        if card is None:
            return None

        if rolled_card.being_rerolled:
            return None  # No buttons while rerolling

        keyboard = []

        if card.owner:
            # Card is claimed - show Lock button if not already locked and not already rerolled
            if not rolled_card.is_locked and not rolled_card.rerolled:
                keyboard.append(
                    [InlineKeyboardButton("Lock", callback_data=f"lock_{self.roll_id}")]
                )
        else:
            # Card is unclaimed - show Claim button
            keyboard.append([InlineKeyboardButton("Claim", callback_data=f"claim_{self.roll_id}")])

        # Add reroll button for both claimed and unclaimed cards (if conditions are met)
        if not rolled_card.is_locked and not rolled_card.rerolled and not self.is_reroll_expired():
            keyboard.append(
                [InlineKeyboardButton("Reroll", callback_data=f"reroll_{self.roll_id}")]
            )

        return InlineKeyboardMarkup(keyboard) if keyboard else None

    def set_being_rerolled(self, being_rerolled: bool) -> None:
        """Set the being_rerolled status in the database."""
        database.set_rolled_card_being_rerolled(self.roll_id, being_rerolled)

    def mark_rerolled(self, new_card_id: Optional[int] = None) -> None:
        """Mark the card as having been rerolled in the database."""
        database.set_rolled_card_rerolled(self.roll_id, new_card_id)

    def set_locked(self, is_locked: bool) -> None:
        """Set the locked status in the database."""
        database.set_rolled_card_locked(self.roll_id, is_locked)

    def add_claim_attempt(self, username: str) -> None:
        """Add a user to the attempted_by list in the database."""
        database.update_rolled_card_attempted_by(self.roll_id, username)
