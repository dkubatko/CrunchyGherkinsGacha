import logging
import random
import time
from dataclasses import dataclass
from typing import Dict, Optional

from settings.constants import RARITIES
from utils import database
from utils.gemini import GeminiUtil
from utils.modifiers import load_modifiers_with_sets, ModifierWithSet

# Store modifiers with their set information
MODIFIERS_WITH_SETS_BY_RARITY: Dict[str, list[ModifierWithSet]] = load_modifiers_with_sets()


logger = logging.getLogger(__name__)


def refresh_modifier_cache() -> None:
    """Reload modifiers from disk. Intended for admin-triggered refreshes."""

    global MODIFIERS_WITH_SETS_BY_RARITY
    MODIFIERS_WITH_SETS_BY_RARITY = load_modifiers_with_sets()


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
    set_id: Optional[int] = None


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


def _choose_modifier_for_rarity(
    rarity: str, chat_id: Optional[str] = None
) -> tuple[ModifierWithSet, float]:
    """Choose a random modifier for the given rarity using weighted selection.

    Modifiers that don't exist in the chat yet get weight 1.0, while existing modifiers
    get weight 1/N where N is the number of times they've been used.

    Args:
        rarity: The rarity level to choose a modifier for
        chat_id: The chat ID to check for existing modifier usage (optional)

    Returns:
        A tuple of (ModifierWithSet, weight) where weight is the selection weight used
    """
    rarity_config = RARITIES.get(rarity)
    if not isinstance(rarity_config, dict):
        raise InvalidSourceError(f"Unsupported rarity '{rarity}'")

    modifiers_with_sets = MODIFIERS_WITH_SETS_BY_RARITY.get(rarity)
    if not modifiers_with_sets:
        raise InvalidSourceError(f"No modifiers configured for rarity '{rarity}'")

    # If no chat_id provided, use uniform random selection
    if chat_id is None:
        chosen = random.choice(modifiers_with_sets)
        return chosen, 1.0

    # Get modifier usage counts for this chat
    modifier_counts = database.get_modifier_counts_for_chat(chat_id)

    # Calculate weights: 1.0 for new modifiers, 1/N for existing ones
    weights = []
    for mod_with_set in modifiers_with_sets:
        count = modifier_counts.get(mod_with_set.modifier, 0)
        if count == 0:
            weights.append(1.0)
        else:
            weights.append(1.0 / count)

    # Choose a modifier using weighted random selection
    chosen = random.choices(modifiers_with_sets, weights=weights, k=1)[0]

    # Get the weight of the chosen modifier for logging
    chosen_index = modifiers_with_sets.index(chosen)
    chosen_weight = weights[chosen_index]

    return chosen, chosen_weight


def _create_generated_card(
    profile: SelectedProfile,
    gemini_util: GeminiUtil,
    rarity: str,
    modifier: Optional[str] = None,
    set_id: Optional[int] = None,
) -> GeneratedCard:
    if rarity not in RARITIES:
        raise InvalidSourceError(f"Unsupported rarity '{rarity}'")

    # If modifier is provided, we need to look up its set_id
    if modifier is not None:
        if set_id is None:
            # Look up the set_id for this specific modifier
            modifiers_with_sets = MODIFIERS_WITH_SETS_BY_RARITY.get(rarity, [])
            for mod_with_set in modifiers_with_sets:
                if mod_with_set.modifier == modifier:
                    set_id = mod_with_set.set_id
                    break
            if set_id is None:
                # Default to 0 if we can't find the modifier (shouldn't happen)
                set_id = 0
        chosen_modifier = modifier
    else:
        # Choose a random modifier and get its set_id (no chat_id, uniform selection)
        modifier_with_set, _ = _choose_modifier_for_rarity(rarity, chat_id=None)
        chosen_modifier = modifier_with_set.modifier
        set_id = modifier_with_set.set_id

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
        set_id=set_id,
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
    chat_id: Optional[str] = None,
) -> GeneratedCard:
    profile = get_profile_for_source(source_type, source_id)

    modifier_with_set, weight = _choose_modifier_for_rarity(rarity, chat_id)

    total_attempts = max(1, max_retries + 1)
    last_error: Optional[Exception] = None

    for attempt in range(1, total_attempts + 1):
        try:
            generated_card = _create_generated_card(
                profile,
                gemini_util,
                rarity,
                modifier=modifier_with_set.modifier,
                set_id=modifier_with_set.set_id,
            )
            logger.info(
                "Successfully generated card for source %s:%s (rarity=%s, modifier=%s, weight=%.2f)",
                source_type,
                source_id,
                rarity,
                modifier_with_set.modifier,
                weight,
            )
            return generated_card
        except ImageGenerationError as exc:
            last_error = exc
            logger.warning(
                "Image generation attempt %s/%s failed for source %s:%s (rarity=%s, modifier=%s, weight=%.2f)",
                attempt,
                total_attempts,
                source_type,
                source_id,
                rarity,
                modifier_with_set.modifier,
                weight,
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
    modifier_with_set, weight = _choose_modifier_for_rarity(chosen_rarity, chat_id)

    total_attempts = max(1, max_retries + 1)
    last_error: Optional[Exception] = None

    for attempt in range(1, total_attempts + 1):
        try:
            generated_card = _create_generated_card(
                profile,
                gemini_util,
                chosen_rarity,
                modifier=modifier_with_set.modifier,
                set_id=modifier_with_set.set_id,
            )
            logger.info(
                "Successfully generated card for chat %s (source=%s:%s, rarity=%s, modifier=%s, weight=%.2f)",
                chat_id,
                profile.source_type,
                profile.source_id,
                chosen_rarity,
                modifier_with_set.modifier,
                weight,
            )
            return generated_card
        except ImageGenerationError as exc:
            last_error = exc
            logger.warning(
                "Image generation attempt %s/%s failed for chat %s (source=%s:%s, rarity=%s, modifier=%s, weight=%.2f)",
                attempt,
                total_attempts,
                chat_id,
                profile.source_type,
                profile.source_id,
                chosen_rarity,
                modifier_with_set.modifier,
                weight,
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
    refresh_attempt: int = 1,
) -> str:
    """
    Regenerate the image for an existing card, keeping the same rarity, modifier, and name.

    Args:
        card: The card to regenerate the image for
        gemini_util: GeminiUtil instance for image generation
        max_retries: Number of retry attempts if generation fails
        refresh_attempt: Which refresh attempt this is (1-3), affects temperature

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
            # Calculate temperature based on refresh attempt (1.0, 1.25, 1.5)
            temperature = 1.0 + (0.25 * (refresh_attempt - 1))

            # Use the existing modifier, rarity and name
            image_b64 = gemini_util.generate_image(
                card.base_name,
                card.modifier,
                card.rarity,
                base_image_b64=profile.image_b64,
                temperature=temperature,
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
