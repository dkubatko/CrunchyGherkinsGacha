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
    source_user: Optional[database.User] = None
    source_character: Optional[database.Character] = None


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


def _create_generated_card(
    profile: SelectedProfile,
    gemini_util: GeminiUtil,
    rarity: str,
) -> GeneratedCard:
    if rarity not in RARITIES:
        raise InvalidSourceError(f"Unsupported rarity '{rarity}'")

    modifier = random.choice(RARITIES[rarity]["modifiers"])

    image_b64 = gemini_util.generate_image(
        profile.name,
        modifier,
        rarity,
        base_image_b64=profile.image_b64,
    )

    if not image_b64:
        raise ImageGenerationError

    source_user = profile.user
    source_character = profile.character

    if source_user is None and profile.source_type == "user" and profile.source_id:
        source_user = database.get_user(profile.source_id)
    if source_character is None and profile.source_type == "character" and profile.source_id:
        source_character = database.get_character_by_id(profile.source_id)

    return GeneratedCard(
        base_name=profile.name,
        modifier=modifier,
        rarity=rarity,
        card_title=f"{modifier} {profile.name}",
        image_b64=image_b64,
        source_user=source_user,
        source_character=source_character,
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
) -> GeneratedCard:
    profile = get_profile_for_source(source_type, source_id)
    return _create_generated_card(profile, gemini_util, rarity)


def generate_card_for_chat(
    chat_id: str,
    gemini_util: GeminiUtil,
    rarity: Optional[str] = None,
) -> GeneratedCard:
    """Generate a card for a chat using a random eligible user's or character's profile image."""
    profile = select_random_source_with_image(chat_id)
    if not profile:
        raise NoEligibleUserError

    chosen_rarity = rarity or get_random_rarity()
    return _create_generated_card(profile, gemini_util, chosen_rarity)
