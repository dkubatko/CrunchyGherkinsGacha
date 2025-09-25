import random
from dataclasses import dataclass
from typing import Optional

from settings.constants import RARITIES
from utils import database
from utils.gemini import GeminiUtil


class NoEligibleUserError(Exception):
    """Raised when no chat members have the required profile image and display name."""


class ImageGenerationError(Exception):
    """Raised when the image generator fails to return data."""


@dataclass
class GeneratedCard:
    base_name: str
    modifier: str
    rarity: str
    card_title: str
    image_b64: str
    source_user: database.User


def select_random_user_with_image(chat_id: str) -> Optional[database.User]:
    """Pick a random enrolled user who has both a profile image and display name."""
    user = database.get_random_chat_user_with_profile(chat_id)
    if not user:
        return None

    display_name = (user.display_name or "").strip()
    profile_image = (user.profile_imageb64 or "").strip()

    if not display_name or not profile_image:
        return None

    # Normalize display name before returning so downstream code can rely on trimmed value.
    user.display_name = display_name
    user.profile_imageb64 = profile_image
    return user


def get_random_rarity() -> str:
    """Return a rarity based on configured weights."""
    rarity_list = list(RARITIES.keys())
    weights = [RARITIES[rarity]["weight"] for rarity in rarity_list]
    return random.choices(rarity_list, weights=weights, k=1)[0]


def get_downgraded_rarity(current_rarity: str) -> str:
    """Return a rarity one level lower than the current rarity."""
    rarity_order = ["Common", "Rare", "Epic", "Legendary"]
    try:
        current_index = rarity_order.index(current_rarity)
    except ValueError:
        return "Common"

    return rarity_order[current_index - 1] if current_index > 0 else "Common"


def generate_card_for_chat(
    chat_id: str,
    gemini_util: GeminiUtil,
    rarity: Optional[str] = None,
) -> GeneratedCard:
    """Generate a card for a chat using a random eligible user's profile image."""
    user = select_random_user_with_image(chat_id)
    if not user:
        raise NoEligibleUserError

    chosen_rarity = rarity or get_random_rarity()
    modifier = random.choice(RARITIES[chosen_rarity]["modifiers"])
    base_name = user.display_name

    image_b64 = gemini_util.generate_image(
        base_name,
        modifier,
        chosen_rarity,
        base_image_b64=user.profile_imageb64,
    )

    if not image_b64:
        raise ImageGenerationError

    return GeneratedCard(
        base_name=base_name,
        modifier=modifier,
        rarity=chosen_rarity,
        card_title=f"{modifier} {base_name}",
        image_b64=image_b64,
        source_user=user,
    )
