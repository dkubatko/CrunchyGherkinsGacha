import logging
import random
import time
from dataclasses import dataclass
from typing import Optional

from settings.constants import RARITIES
from utils import database
from utils.gemini import GeminiUtil


logger = logging.getLogger(__name__)


class NoEligibleUserError(Exception):
    """Raised when no chat members have the required profile image and display name."""


class ImageGenerationError(Exception):
    """Raised when the image generator fails to return data."""


class InvalidSourceError(Exception):
    """Raised when an invalid or unsupported source type/id is provided."""


@dataclass
class SelectedProfile:
    """A profile selected for card generation, either from a user or character."""

    name: str
    image_b64: str
    source_type: str  # "user" or "character"
    source_id: Optional[int] = None  # user_id for users, character id for characters
    user: Optional[database.User] = None
    character: Optional[database.Character] = None


@dataclass
class GeneratedCard:
    base_name: str
    modifier: str
    rarity: str
    card_title: str
    image_b64: str
    source_type: str
    source_id: int


def select_random_source_with_image(chat_id: str) -> Optional[SelectedProfile]:
    """Pick a random source (user or character) that can be used for card generation."""
    # Get all eligible users from the chat
    eligible_users = database.get_all_chat_users_with_profile(chat_id)

    # Create SelectedProfile objects for all eligible users
    user_profiles = []
    for user in eligible_users:
        display_name = (user.display_name or "").strip()
        profile_image = (user.profile_imageb64 or "").strip()

        if display_name and profile_image:
            user_profiles.append(
                SelectedProfile(
                    name=display_name,
                    image_b64=profile_image,
                    source_type="user",
                    source_id=user.user_id,
                    user=user,
                )
            )

    # Get all characters for this chat and create SelectedProfile objects
    characters = database.get_characters_by_chat(chat_id)
    character_profiles = [
        SelectedProfile(
            name=char.name,
            image_b64=char.imageb64,
            source_type="character",
            source_id=char.id,
            character=char,
        )
        for char in characters
    ]

    # Combine all profiles
    all_profiles = user_profiles + character_profiles

    if not all_profiles:
        return None

    return random.choice(all_profiles)


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


def _choose_modifier_for_rarity(rarity: str) -> str:
    rarity_config = RARITIES.get(rarity)
    if not isinstance(rarity_config, dict):
        raise InvalidSourceError(f"Unsupported rarity '{rarity}'")

    modifiers = rarity_config.get("modifiers")
    if not modifiers:
        raise InvalidSourceError(f"No modifiers configured for rarity '{rarity}'")

    return random.choice(modifiers)


def _create_generated_card(
    profile: SelectedProfile,
    gemini_util: GeminiUtil,
    rarity: str,
    modifier: Optional[str] = None,
) -> GeneratedCard:
    if rarity not in RARITIES:
        raise InvalidSourceError(f"Unsupported rarity '{rarity}'")

    chosen_modifier = modifier if modifier is not None else _choose_modifier_for_rarity(rarity)

    image_b64 = gemini_util.generate_image(
        profile.name,
        chosen_modifier,
        rarity,
        base_image_b64=profile.image_b64,
    )

    if not image_b64:
        raise ImageGenerationError

    return GeneratedCard(
        base_name=profile.name,
        modifier=chosen_modifier,
        rarity=rarity,
        card_title=f"{chosen_modifier} {profile.name}",
        image_b64=image_b64,
        source_type=profile.source_type,
        source_id=profile.source_id,
    )


def get_profile_for_source(source_type: str, source_id: int) -> SelectedProfile:
    normalized_type = (source_type or "").strip().lower()

    if normalized_type == "user":
        user = database.get_user(source_id)
        if not user:
            raise InvalidSourceError(f"User {source_id} not found")

        display_name = (user.display_name or "").strip()
        image_b64 = (user.profile_imageb64 or "").strip()

        if not display_name or not image_b64:
            raise NoEligibleUserError

        return SelectedProfile(
            name=display_name,
            image_b64=image_b64,
            source_type="user",
            source_id=user.user_id,
            user=user,
        )

    if normalized_type == "character":
        character = database.get_character_by_id(source_id)
        if not character:
            raise InvalidSourceError(f"Character {source_id} not found")

        name = (character.name or "").strip()
        image_b64 = (character.imageb64 or "").strip()

        if not name or not image_b64:
            raise NoEligibleUserError

        return SelectedProfile(
            name=name,
            image_b64=image_b64,
            source_type="character",
            source_id=character.id,
            character=character,
        )

    raise InvalidSourceError(f"Unsupported source type '{source_type}'")


def generate_card_from_source(
    source_type: str,
    source_id: int,
    gemini_util: GeminiUtil,
    rarity: str,
    max_retries: int = 0,
) -> GeneratedCard:
    profile = get_profile_for_source(source_type, source_id)

    chosen_modifier = _choose_modifier_for_rarity(rarity)

    total_attempts = max(1, max_retries + 1)
    last_error: Optional[Exception] = None

    for attempt in range(1, total_attempts + 1):
        try:
            return _create_generated_card(
                profile,
                gemini_util,
                rarity,
                modifier=chosen_modifier,
            )
        except ImageGenerationError as exc:
            last_error = exc
            logger.warning(
                "Image generation attempt %s/%s failed for source %s:%s (rarity=%s, modifier=%s)",
                attempt,
                total_attempts,
                source_type,
                source_id,
                rarity,
                chosen_modifier,
            )

            if attempt < total_attempts:
                time.sleep(1)

    raise last_error or ImageGenerationError("Image generation failed after retries")


def generate_card_for_chat(
    chat_id: str,
    gemini_util: GeminiUtil,
    rarity: Optional[str] = None,
    max_retries: int = 0,
) -> GeneratedCard:
    """Generate a card for a chat using a random eligible user's or character's profile image."""
    profile = select_random_source_with_image(chat_id)
    if not profile:
        raise NoEligibleUserError

    chosen_rarity = rarity or get_random_rarity()
    chosen_modifier = _choose_modifier_for_rarity(chosen_rarity)

    total_attempts = max(1, max_retries + 1)
    last_error: Optional[Exception] = None

    for attempt in range(1, total_attempts + 1):
        try:
            return _create_generated_card(
                profile,
                gemini_util,
                chosen_rarity,
                modifier=chosen_modifier,
            )
        except ImageGenerationError as exc:
            last_error = exc
            logger.warning(
                "Image generation attempt %s/%s failed for chat %s (source=%s:%s, rarity=%s, modifier=%s)",
                attempt,
                total_attempts,
                chat_id,
                profile.source_type,
                profile.source_id,
                chosen_rarity,
                chosen_modifier,
            )

            if attempt < total_attempts:
                time.sleep(1)
                refreshed_profile = select_random_source_with_image(chat_id)
                if refreshed_profile:
                    profile = refreshed_profile

    raise last_error or ImageGenerationError("Image generation failed after retries")


def regenerate_card_image(
    card: database.Card,
    gemini_util: GeminiUtil,
    max_retries: int = 0,
) -> str:
    """
    Regenerate the image for an existing card, keeping the same rarity, modifier, and name.

    Args:
        card: The card to regenerate the image for
        gemini_util: GeminiUtil instance for image generation
        max_retries: Number of retry attempts if generation fails

    Returns:
        The new base64-encoded image

    Raises:
        InvalidSourceError: If the card has no valid source
        NoEligibleUserError: If the source user/character is missing required data
        ImageGenerationError: If image generation fails after retries
    """
    # Check that the card has source information
    if not card.source_type or not card.source_id:
        raise InvalidSourceError(
            f"Card {card.id} has no source information (source_type={card.source_type}, source_id={card.source_id})"
        )

    # Get the source profile using the stored source_type and source_id
    profile = get_profile_for_source(card.source_type, card.source_id)

    # Now regenerate with the same rarity and modifier
    total_attempts = max(1, max_retries + 1)
    last_error: Optional[Exception] = None

    for attempt in range(1, total_attempts + 1):
        try:
            # Use the existing modifier, rarity and name
            image_b64 = gemini_util.generate_image(
                card.base_name,
                card.modifier,
                card.rarity,
                base_image_b64=profile.image_b64,
            )

            if not image_b64:
                raise ImageGenerationError("Empty image returned")

            logger.info(
                "Successfully regenerated image for card %s (attempt %s/%s)",
                card.id,
                attempt,
                total_attempts,
            )
            return image_b64

        except Exception as exc:
            last_error = exc
            logger.warning(
                "Image regeneration attempt %s/%s failed for card %s: %s",
                attempt,
                total_attempts,
                card.id,
                exc,
            )

            if attempt < total_attempts:
                time.sleep(1)

    raise last_error or ImageGenerationError("Image regeneration failed after retries")
