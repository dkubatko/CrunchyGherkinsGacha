import logging
import random
import time
from dataclasses import dataclass
from typing import Dict, Optional

from settings.constants import RARITIES, UNIQUE_ADDENDUM
from utils.services import card_service, character_service, user_service, set_service
from utils.schemas import Card, Character, User
from utils.gemini import GeminiUtil
from utils.modifiers import load_modifiers_with_sets, ModifierWithSet, get_modifier_info

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
    user: Optional[User] = None
    character: Optional[Character] = None


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
    set_name: str = ""


def select_random_source_with_image(chat_id: str) -> Optional[SelectedProfile]:
    """Pick a random source (user or character) that can be used for card generation."""
    # Get all eligible users from the chat
    eligible_users = user_service.get_all_chat_users_with_profile(chat_id)

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
    characters = character_service.get_characters_by_chat(chat_id)
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


def select_random_user_with_image(chat_id: str) -> Optional[User]:
    """Pick a random enrolled user who has both a profile image and display name."""
    user = user_service.get_random_chat_user_with_profile(chat_id)
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


def get_random_rarity(source: Optional[str] = None) -> str:
    """Return a rarity based on configured weights.

    Args:
        source: The source for weight selection ("roll" or "slots").
                Defaults to "roll" if not specified.
    """
    weight_key = "slots_weight" if source == "slots" else "roll_weight"
    rarity_list = [
        r
        for r in RARITIES.keys()
        if isinstance(RARITIES[r], dict) and RARITIES[r].get(weight_key, 0) > 0
    ]

    if not rarity_list:
        return "Common"

    weights = [RARITIES[r][weight_key] for r in rarity_list]
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
    rarity: str, chat_id: Optional[str] = None, source: Optional[str] = None
) -> tuple[ModifierWithSet, float]:
    """Choose a random modifier for the given rarity using weighted selection.

    Modifiers that don't exist in the chat yet get weight 1.0, while existing modifiers
    get weight 1/N where N is the number of times they've been used.

    Args:
        rarity: The rarity level to choose a modifier for
        chat_id: The chat ID to check for existing modifier usage (optional)
        source: Filter modifiers by source ("roll" or "slots"). Sets with "all" source
                qualify for any source. If None, no source filtering is applied.

    Returns:
        A tuple of (ModifierWithSet, weight) where weight is the selection weight used
    """
    rarity_config = RARITIES.get(rarity)
    if not isinstance(rarity_config, dict):
        raise InvalidSourceError(f"Unsupported rarity '{rarity}'")

    modifiers_with_sets = MODIFIERS_WITH_SETS_BY_RARITY.get(rarity)
    if not modifiers_with_sets:
        raise InvalidSourceError(f"No modifiers configured for rarity '{rarity}'")

    # Filter by source if specified
    if source is not None:
        modifiers_with_sets = [
            mod for mod in modifiers_with_sets if mod.source == "all" or mod.source == source
        ]
        if not modifiers_with_sets:
            raise InvalidSourceError(
                f"No modifiers configured for rarity '{rarity}' with source '{source}'"
            )

    # If no chat_id provided, use uniform random selection
    if chat_id is None:
        chosen = random.choice(modifiers_with_sets)
        return chosen, 1.0

    # Get modifier usage counts for this chat
    modifier_counts = card_service.get_modifier_counts_for_chat(chat_id)

    # Get unique modifiers to exclude
    unique_modifiers = set(card_service.get_unique_modifiers(chat_id))

    # Calculate weights: 1.0 for new modifiers, 1/N for existing ones
    weights = []
    valid_modifiers = []

    for mod_with_set in modifiers_with_sets:
        if mod_with_set.modifier in unique_modifiers:
            continue

        valid_modifiers.append(mod_with_set)
        count = modifier_counts.get(mod_with_set.modifier, 0)
        if count == 0:
            weights.append(1.0)
        else:
            weights.append(1.0 / count)

    if not valid_modifiers:
        # Fallback if all modifiers are excluded
        valid_modifiers = modifiers_with_sets
        weights = [1.0] * len(valid_modifiers)

    # Choose a modifier using weighted random selection
    chosen = random.choices(valid_modifiers, weights=weights, k=1)[0]

    # Get the weight of the chosen modifier for logging
    chosen_index = valid_modifiers.index(chosen)
    chosen_weight = weights[chosen_index]

    logger.info(
        "Chose modifier '%s' (set=%s, weight=%.2f) for rarity=%s, source=%s, chat=%s",
        chosen.modifier,
        chosen.set_id,
        chosen_weight,
        rarity,
        source or "any",
        chat_id or "none",
    )

    return chosen, chosen_weight


def _create_generated_card(
    profile: SelectedProfile,
    gemini_util: GeminiUtil,
    rarity: str,
    modifier_info: ModifierWithSet,
) -> GeneratedCard:
    """Generate a card image and return a GeneratedCard.

    Args:
        profile: The source profile (user or character) for the card.
        gemini_util: GeminiUtil instance for image generation.
        rarity: The rarity level for the card.
        modifier_info: The modifier with its set information.

    Returns:
        A GeneratedCard with the generated image.

    Raises:
        InvalidSourceError: If the rarity is not supported.
        ImageGenerationError: If image generation fails.
    """
    if rarity not in RARITIES:
        raise InvalidSourceError(f"Unsupported rarity '{rarity}'")

    image_b64 = gemini_util.generate_image(
        profile.name,
        modifier_info.modifier,
        rarity,
        base_image_b64=profile.image_b64,
        set_name=modifier_info.set_name,
    )

    if not image_b64:
        raise ImageGenerationError

    return GeneratedCard(
        base_name=profile.name,
        modifier=modifier_info.modifier,
        rarity=rarity,
        card_title=f"{modifier_info.modifier} {profile.name}",
        image_b64=image_b64,
        source_type=profile.source_type,
        source_id=profile.source_id,
        set_id=modifier_info.set_id,
        set_name=modifier_info.set_name,
    )


def get_profile_for_source(source_type: str, source_id: int) -> SelectedProfile:
    normalized_type = (source_type or "").strip().lower()

    if normalized_type == "user":
        user = user_service.get_user(source_id)
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
        character = character_service.get_character_by_id(source_id)
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


def generate_card_from_profile(
    profile_type: str,
    profile_id: int,
    gemini_util: GeminiUtil,
    rarity: str,
    max_retries: int = 0,
    chat_id: Optional[str] = None,
    source: Optional[str] = None,
) -> GeneratedCard:
    profile = get_profile_for_source(profile_type, profile_id)

    modifier_with_set, weight = _choose_modifier_for_rarity(rarity, chat_id, source=source)

    total_attempts = max(1, max_retries + 1)
    last_error: Optional[Exception] = None

    for attempt in range(1, total_attempts + 1):
        try:
            generated_card = _create_generated_card(
                profile,
                gemini_util,
                rarity,
                modifier_info=modifier_with_set,
            )
            logger.info(
                "Successfully generated card for profile %s:%s (rarity=%s, modifier=%s, weight=%.2f)",
                profile_type,
                profile_id,
                rarity,
                modifier_with_set.modifier,
                weight,
            )
            return generated_card
        except ImageGenerationError as exc:
            last_error = exc
            logger.warning(
                "Image generation attempt %s/%s failed for profile %s:%s (rarity=%s, modifier=%s, weight=%.2f)",
                attempt,
                total_attempts,
                profile_type,
                profile_id,
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
    source: Optional[str] = None,
) -> GeneratedCard:
    """Generate a card for a chat using a random eligible user's or character's profile image.

    Args:
        chat_id: The chat ID to generate the card for.
        gemini_util: The Gemini utility for image generation.
        rarity: Optional rarity override. If None, uses weighted random selection.
        max_retries: Number of additional attempts on image generation failure.
        source: Source filter for modifiers ("roll" or "slots"). Defaults to None (no filtering).
    """
    profile = select_random_source_with_image(chat_id)
    if not profile:
        raise NoEligibleUserError

    chosen_rarity = rarity or get_random_rarity(source)
    modifier_with_set, weight = _choose_modifier_for_rarity(chosen_rarity, chat_id, source=source)

    total_attempts = max(1, max_retries + 1)
    last_error: Optional[Exception] = None

    for attempt in range(1, total_attempts + 1):
        try:
            generated_card = _create_generated_card(
                profile,
                gemini_util,
                chosen_rarity,
                modifier_info=modifier_with_set,
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
    card: Card,
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

    # Get the set_name from the card's set_id
    set_name = ""
    if card.set_id is not None:
        set_model = set_service.get_set_by_id(card.set_id)
        if set_model:
            set_name = set_model.name

    # Now regenerate with the same rarity and modifier
    total_attempts = max(1, max_retries + 1)
    last_error: Optional[Exception] = None

    for attempt in range(1, total_attempts + 1):
        try:
            # Calculate temperature based on refresh attempt (1.0, 1.25, 1.5)
            temperature = 1.0 + (0.25 * (refresh_attempt - 1))

            # Add UNIQUE_ADDENDUM for Unique rarity cards
            instruction_addendum = UNIQUE_ADDENDUM if card.rarity == "Unique" else ""

            # Use the existing modifier, rarity and name
            image_b64 = gemini_util.generate_image(
                card.base_name,
                card.modifier,
                card.rarity,
                base_image_b64=profile.image_b64,
                temperature=temperature,
                instruction_addendum=instruction_addendum,
                set_name=set_name,
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


def find_profile_by_name(chat_id: str, name: str) -> Optional[SelectedProfile]:
    """Find a profile (user or character) by name in the chat."""
    name_lower = name.strip().lower()

    # Check characters first
    characters = character_service.get_characters_by_chat(chat_id)
    for char in characters:
        if char.name.strip().lower() == name_lower:
            return SelectedProfile(
                name=char.name,
                image_b64=char.imageb64,
                source_type="character",
                source_id=char.id,
                character=char,
            )

    # Check users
    users = user_service.get_all_chat_users_with_profile(chat_id)
    for user in users:
        display_name = (user.display_name or "").strip()
        if display_name.lower() == name_lower:
            return SelectedProfile(
                name=display_name,
                image_b64=user.profile_imageb64,
                source_type="user",
                source_id=user.user_id,
                user=user,
            )

    return None


def generate_unique_card(
    modifier: str,
    profile: SelectedProfile,
    gemini_util: GeminiUtil,
    instruction_addendum: str,
    max_retries: int = 0,
) -> GeneratedCard:
    """Generate a Unique card with a specific modifier and profile."""
    rarity = "Unique"

    total_attempts = max(1, max_retries + 1)
    last_error: Optional[Exception] = None

    for attempt in range(1, total_attempts + 1):
        try:
            image_b64 = gemini_util.generate_image(
                profile.name,
                modifier,
                rarity,
                base_image_b64=profile.image_b64,
                instruction_addendum=instruction_addendum,
            )

            if not image_b64:
                raise ImageGenerationError("Empty image returned")

            return GeneratedCard(
                base_name=profile.name,
                modifier=modifier,
                rarity=rarity,
                card_title=f"{modifier} {profile.name}",
                image_b64=image_b64,
                source_type=profile.source_type,
                source_id=profile.source_id,
                set_id=None,  # Unique cards don't belong to a set usually, or we can assign one if needed
                set_name="",
            )
        except Exception as e:
            logger.error(f"Error generating unique card (attempt {attempt}/{total_attempts}): {e}")
            last_error = e

    raise last_error or ImageGenerationError("Image generation failed after retries")
