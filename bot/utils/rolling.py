import logging
import random
import time
from dataclasses import dataclass
from typing import List, Literal, Optional

from settings.constants import CURRENT_SEASON, RARITIES, ROLL_TYPE_WEIGHTS
from repos import user_repo
from repos import character_repo
from repos import aspect_repo
from repos import aspect_count_repo
from utils.schemas import AspectDefinition, Character, User
from utils.models import UserModel, CharacterModel
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
    user: Optional[User] = None
    character: Optional[Character] = None


@dataclass
class GeneratedCard:
    base_name: str
    modifier: Optional[str]
    rarity: str
    card_title: str
    image_b64: str
    source_type: str
    source_id: int
    set_id: Optional[int] = None
    set_name: str = ""
    description: Optional[str] = None


@dataclass
class GeneratedAspect:
    """Result of generating an aspect sphere image."""

    aspect_id: int  # DB id of the OwnedAspectModel created for this roll
    aspect_name: str
    rarity: str
    image_b64: str
    set_name: str = ""
    set_id: Optional[int] = None
    aspect_definition_id: Optional[int] = None
    set_description: str = ""


@dataclass
class RollResult:
    """Tagged union of a roll outcome: either a base card or an aspect."""

    roll_type: Literal["base_card", "aspect"]
    card: Optional[GeneratedCard] = None
    aspect: Optional[GeneratedAspect] = None


def select_random_source_with_image(chat_id: str) -> Optional[SelectedProfile]:
    """Pick a random source (user or character) that can be used for card generation."""
    # Get all eligible users from the chat
    eligible_users = user_repo.get_all_chat_users_with_profile(chat_id)

    # Create SelectedProfile objects for all eligible users
    user_profiles = []
    for user in eligible_users:
        display_name = (user.display_name or "").strip()
        profile_image = (user.profile_image_b64 or "").strip()

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
    characters = character_repo.get_characters_by_chat(chat_id)
    character_profiles = [
        SelectedProfile(
            name=char.name,
            image_b64=char.image_b64,
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


def _choose_aspect_definition_for_rarity(
    rarity: str,
    chat_id: Optional[str] = None,
    source: Optional[str] = None,
) -> AspectDefinition:
    """Choose a random aspect definition for the given rarity using weighted selection.

    Mirrors ``_choose_modifier_for_rarity`` but queries ``aspect_definitions``
    instead of ``modifiers`` and uses ``aspect_count_service`` for weighting.

    Args:
        rarity: The rarity level to choose an aspect definition for.
        chat_id: The chat ID to check for existing usage (optional).
        source: Filter definitions by source ("roll" or "slots").

    Returns:
        An ``AspectDefinition`` schema instance.

    Raises:
        InvalidSourceError: If no aspect definitions exist for the rarity.
    """
    defs_by_rarity = aspect_repo.get_aspect_definitions_by_rarity(source=source)
    definitions = defs_by_rarity.get(rarity)
    if not definitions:
        raise InvalidSourceError(f"No aspect definitions configured for rarity '{rarity}'")

    # Uniform selection when no chat context
    if chat_id is None:
        return random.choice(definitions)

    # Weighted selection: 1/(1+count) favoring unseen definitions
    counts = aspect_count_repo.get_counts(chat_id)

    weights: List[float] = []
    for ad in definitions:
        count = counts.get(ad.name, 0)
        weights.append(1.0 / (1 + count))

    chosen = random.choices(definitions, weights=weights, k=1)[0]
    chosen_weight = weights[definitions.index(chosen)]

    logger.info(
        "Chose aspect definition '%s' (id=%s, set='%s', weight=%.2f) "
        "for rarity=%s, source=%s, chat=%s",
        chosen.name,
        chosen.id,
        chosen.set_name,
        chosen_weight,
        rarity,
        source or "any",
        chat_id or "none",
    )

    return chosen


def get_profile_for_source(source_type: str, source_id: int) -> SelectedProfile:
    normalized_type = (source_type or "").strip().lower()

    if normalized_type == "user":
        user = user_repo.get_user(source_id)
        if not user:
            raise InvalidSourceError(f"User {source_id} not found")

        display_name = (user.display_name or "").strip()
        image_b64 = (user.profile_image_b64 or "").strip()

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
        character = character_repo.get_character_by_id(source_id)
        if not character:
            raise InvalidSourceError(f"Character {source_id} not found")

        name = (character.name or "").strip()
        image_b64 = (character.image_b64 or "").strip()

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


def generate_base_card(
    gemini_util: GeminiUtil,
    rarity: str,
    max_retries: int = 0,
    chat_id: Optional[str] = None,
    profile_type: Optional[str] = None,
    profile_id: Optional[int] = None,
) -> GeneratedCard:
    """Generate a base card (no modifier/theme).

    Can be called in two modes:

    1. **Known source** (``profile_type`` + ``profile_id`` provided):
       Resolves the source and generates a card for it.  Used by slots /
       megaspin victories where the source is already determined.

    2. **Random source** (only ``chat_id`` provided):
       Picks a random eligible profile from the chat.  On retry, re-selects
       a fresh profile in case the previous one was problematic.  Used by
       the ``/roll`` pipeline and reroll flow.

    Args:
        gemini_util: GeminiUtil instance for image generation.
        rarity: The rarity level for the card.
        max_retries: Number of additional attempts on failure.
        chat_id: Chat to pick a random source from (mode 2).
        profile_type: ``"user"`` or ``"character"`` (mode 1).
        profile_id: The user_id or character id (mode 1).

    Returns:
        A ``GeneratedCard`` with ``modifier=None``.
    """
    random_mode = profile_type is None or profile_id is None

    if random_mode:
        if chat_id is None:
            raise ValueError("chat_id is required when profile_type/profile_id are not provided")
        profile = select_random_source_with_image(chat_id)
        if not profile:
            raise NoEligibleUserError
    else:
        profile = get_profile_for_source(profile_type, profile_id)

    total_attempts = max(1, max_retries + 1)
    last_error: Optional[Exception] = None

    for attempt in range(1, total_attempts + 1):
        try:
            image_b64 = gemini_util.generate_image(
                profile.name,
                rarity,
                base_image_b64=profile.image_b64,
            )
            if not image_b64:
                raise ImageGenerationError

            logger.info(
                "Successfully generated base card (source=%s:%s, rarity=%s, chat=%s)",
                profile.source_type,
                profile.source_id,
                rarity,
                chat_id or "n/a",
            )

            return GeneratedCard(
                base_name=profile.name,
                modifier=None,
                rarity=rarity,
                card_title=profile.name,
                image_b64=image_b64,
                source_type=profile.source_type,
                source_id=profile.source_id,
            )
        except ImageGenerationError as exc:
            last_error = exc
            logger.warning(
                "Base card generation attempt %s/%s failed (source=%s:%s, rarity=%s, chat=%s)",
                attempt,
                total_attempts,
                profile.source_type,
                profile.source_id,
                rarity,
                chat_id or "n/a",
            )
            if attempt < total_attempts:
                time.sleep(1)
                if random_mode:
                    refreshed = select_random_source_with_image(chat_id)
                    if refreshed:
                        profile = refreshed

    raise last_error or ImageGenerationError("Base card generation failed after retries")


def _determine_roll_type() -> str:
    """Determine whether this roll produces a base card or an aspect.

    Uses ``ROLL_TYPE_WEIGHTS`` from config.  Returns ``"base_card"`` or
    ``"aspect"``.
    """
    types = list(ROLL_TYPE_WEIGHTS.keys())
    weights = [ROLL_TYPE_WEIGHTS[t] for t in types]
    return random.choices(types, weights=weights, k=1)[0]


def generate_aspect_for_chat(
    chat_id: str,
    gemini_util: GeminiUtil,
    rarity: str,
    max_retries: int = 0,
    source: Optional[str] = None,
) -> GeneratedAspect:
    """Generate an aspect sphere for a chat.

    Selects an aspect definition, generates the sphere image via Gemini,
    creates the ``OwnedAspectModel`` (unclaimed), and returns a
    ``GeneratedAspect``.

    Used by the main roll pipeline and the recycle-aspect flow.
    """
    aspect_def = _choose_aspect_definition_for_rarity(rarity, chat_id, source=source)

    total_attempts = max(1, max_retries + 1)
    last_error: Optional[Exception] = None

    for attempt in range(1, total_attempts + 1):
        try:
            image_b64 = gemini_util.generate_aspect_image(
                aspect_name=aspect_def.name,
                rarity=rarity,
                set_name=aspect_def.set_name,
                set_description=aspect_def.description or None,
            )
            if not image_b64:
                raise ImageGenerationError("Empty aspect image returned")

            # Create the owned aspect in DB (unclaimed — owner/user_id = None)
            import base64 as _b64

            image_bytes = _b64.b64decode(image_b64)
            from utils.image import ImageUtil

            thumbnail_bytes = ImageUtil.compress_to_fraction(image_bytes)

            aspect_id = aspect_repo.add_owned_aspect(
                aspect_definition_id=aspect_def.id,
                chat_id=str(chat_id),
                season_id=CURRENT_SEASON,
                rarity=rarity,
                image=image_bytes,
                thumbnail=thumbnail_bytes,
                owner=None,
                user_id=None,
            )

            logger.info(
                "Successfully generated aspect for chat %s (aspect_def='%s', "
                "id=%s, rarity=%s, set='%s')",
                chat_id,
                aspect_def.name,
                aspect_id,
                rarity,
                aspect_def.set_name,
            )

            return GeneratedAspect(
                aspect_id=aspect_id,
                aspect_name=aspect_def.name,
                rarity=rarity,
                image_b64=image_b64,
                set_name=aspect_def.set_name or "",
                set_id=aspect_def.set_id,
                aspect_definition_id=aspect_def.id,
                set_description=aspect_def.description or "",
            )
        except ImageGenerationError as exc:
            last_error = exc
            logger.warning(
                "Aspect generation attempt %s/%s failed for chat %s "
                "(aspect_def='%s', rarity=%s)",
                attempt,
                total_attempts,
                chat_id,
                aspect_def.name,
                rarity,
            )
            if attempt < total_attempts:
                time.sleep(1)

    raise last_error or ImageGenerationError("Aspect generation failed after retries")


def generate_roll_for_chat(
    chat_id: str,
    gemini_util: GeminiUtil,
    rarity: Optional[str] = None,
    max_retries: int = 0,
    source: Optional[str] = None,
    roll_type: Optional[str] = None,
    profile_type: Optional[str] = None,
    profile_id: Optional[int] = None,
) -> RollResult:
    """Roll for the chat, producing either a base card or an aspect.

    Args:
        chat_id: The chat ID.
        gemini_util: GeminiUtil instance.
        rarity: Optional rarity override.  If None, uses weighted random.
        max_retries: Extra generation attempts on failure.
        source: Source filter for definitions ("roll", "slots", etc.).
        roll_type: Force a specific roll type ("base_card" or "aspect").
                   If None, determined by ``ROLL_TYPE_WEIGHTS``.
        profile_type: Force a specific profile source ("user" or "character").
        profile_id: The user_id or character id to use with profile_type.

    Returns:
        A ``RollResult`` with either ``.card`` or ``.aspect`` populated.
    """
    chosen_type = roll_type or _determine_roll_type()
    chosen_rarity = rarity or get_random_rarity(source)

    if chosen_type == "base_card":
        card = generate_base_card(
            gemini_util,
            chosen_rarity,
            max_retries,
            chat_id=chat_id,
            profile_type=profile_type,
            profile_id=profile_id,
        )
        return RollResult(roll_type="base_card", card=card)
    else:
        aspect = generate_aspect_for_chat(
            chat_id, gemini_util, chosen_rarity, max_retries, source=source
        )
        return RollResult(roll_type="aspect", aspect=aspect)


def regenerate_card_image(
    card,
    gemini_util: GeminiUtil,
    max_retries: int = 0,
    refresh_attempt: int = 1,
) -> str:
    """Regenerate the image for an existing base card.

    Produces a fresh image using ``BASE_CARD_GENERATION_PROMPT`` and the
    source profile's photo.  For cards with equipped aspects, the caller
    should use the equipped-refresh path instead
    (see ``_generate_equipped_refresh_options`` in ``handlers/cards.py``).

    Args:
        card: The card to regenerate (must have ``source_type`` / ``source_id``).
        gemini_util: GeminiUtil instance for image generation.
        max_retries: Number of retry attempts if generation fails.
        refresh_attempt: Which refresh attempt this is (1-3), affects temperature.

    Returns:
        The new base64-encoded image.

    Raises:
        InvalidSourceError: If the card has no valid source.
        NoEligibleUserError: If the source user/character is missing required data.
        ImageGenerationError: If image generation fails after retries.
    """
    if not card.source_type or not card.source_id:
        raise InvalidSourceError(
            f"Card {card.id} has no source information "
            f"(source_type={card.source_type}, source_id={card.source_id})"
        )

    profile = get_profile_for_source(card.source_type, card.source_id)

    total_attempts = max(1, max_retries + 1)
    last_error: Optional[Exception] = None

    for attempt in range(1, total_attempts + 1):
        try:
            temperature = 1.0 + (0.25 * (refresh_attempt - 1))

            image_b64 = gemini_util.generate_image(
                card.base_name,
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
