import base64
import logging
import os
import random
from io import BytesIO

from google import genai
from google.genai import types
from PIL import Image

from settings.constants import (
    ASPECT_GENERATION_PROMPT,
    ASPECT_SET_CONTEXT,
    ASPECT_TYPE_CONTEXT,
    BASE_CARD_GENERATION_PROMPT,
    CARD_WITH_ASPECTS_PROMPT,
    RARITIES,
    CARD_TEMPLATES_PATH,
    SLOT_MACHINE_INSTRUCTION,
    UNIQUE_ASPECT_ADDENDUM,
)
from utils.image import ImageUtil

logger = logging.getLogger(__name__)


class GeminiUtil:
    def __init__(self, google_api_key: str, image_gen_model: str):
        """
        Initialize GeminiUtil with configuration.

        Args:
            google_api_key: Google API key for Gemini
            image_gen_model: Model name for image generation
        """
        self.client = genai.Client(api_key=google_api_key)
        self.model_name = image_gen_model

        # Configure safety settings to be least restrictive
        self.safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
        ]
        logger.info(f"GeminiUtil initialized with model {image_gen_model}")

    @staticmethod
    def _prepare_image_part(
        image_path: str | None = None,
        image_b64: str | None = None,
        image_bytes: bytes | None = None,
        max_size: int = 768,
    ) -> types.Part:
        """
        Load, downscale, and convert an image to a Gemini Part ready for sending.

        Accepts one of image_path, image_b64, or raw image_bytes.
        Returns a types.Part with media_resolution set to LOW.
        """
        if image_path:
            img = Image.open(image_path)
        elif image_b64:
            img = Image.open(BytesIO(base64.b64decode(image_b64)))
        elif image_bytes:
            img = Image.open(BytesIO(image_bytes))
        else:
            raise ValueError("One of image_path, image_b64, or image_bytes must be provided.")

        img.thumbnail((max_size, max_size), Image.LANCZOS)

        buf = BytesIO()
        img.save(buf, format="PNG")
        return types.Part.from_bytes(
            data=buf.getvalue(),
            mime_type="image/png",
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_MEDIUM,
        )

    def generate_image(
        self,
        base_name: str,
        rarity: str,
        base_image_path: str | None = None,
        base_image_b64: str | None = None,
        temperature: float = 1.0,
        instruction_addendum: str = "",
    ):
        try:
            if base_image_path is None and base_image_b64 is None:
                raise ValueError("Either base_image_path or base_image_b64 must be provided.")

            prompt = BASE_CARD_GENERATION_PROMPT.format(
                name=base_name,
                rarity=rarity,
                color=RARITIES[rarity]["color"],
                creativeness_factor=RARITIES[rarity]["creativeness_factor"],
            )
            if instruction_addendum:
                prompt += instruction_addendum

            logger.info(
                f"Requesting base card image generation for '{base_name}', rarity '{rarity}' (temperature {temperature})"
            )

            template_image_path = os.path.join(CARD_TEMPLATES_PATH, f"{rarity.lower()}.png")
            template_part = self._prepare_image_part(image_path=template_image_path)
            img_part = self._prepare_image_part(
                image_path=base_image_path, image_b64=base_image_b64
            )

            config = types.GenerateContentConfig(
                temperature=temperature,
                safety_settings=self.safety_settings,
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(image_size="1K"),
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt, template_part, img_part],
                config=config,
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    image_bytes = ImageUtil.to_jpeg(image_bytes)
                    processed_image_bytes = ImageUtil.crop_to_content(image_bytes)
                    processed_image_bytes = ImageUtil.crop_to_aspect_ratio(processed_image_bytes, 5/7)
                    logger.info(f"Image for '{base_name}' generated and processed successfully.")
                    return base64.b64encode(processed_image_bytes).decode("utf-8")
            logger.warning("No image data found in response.")
            return None
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return None

    def generate_slot_machine_icon(
        self,
        base_image_path: str | None = None,
        base_image_b64: str | None = None,
        target_size: int = 256,
    ):
        """
        Generate a 1:1 aspect ratio slot machine icon from a user's image.

        Args:
            base_image_path: Path to base image file
            base_image_b64: Base64-encoded base image
            target_size: Target size for the output icon (default 256x256)
        """
        try:
            if base_image_path is None and base_image_b64 is None:
                raise ValueError("Either base_image_path or base_image_b64 must be provided.")

            # Generate slot machine icon with casino styling
            prompt = SLOT_MACHINE_INSTRUCTION
            logger.info("Requesting slot machine icon generation with casino styling")

            # Prepare the source image and crop to 1:1 aspect ratio
            if base_image_b64:
                source_bytes = base64.b64decode(base_image_b64)
            else:
                with open(base_image_path, "rb") as f:
                    source_bytes = f.read()

            # Crop to square (1:1) aspect ratio before sending to Gemini
            square_image_bytes = ImageUtil.crop_to_square(source_bytes)
            img_part = self._prepare_image_part(image_bytes=square_image_bytes)

            config = types.GenerateContentConfig(
                safety_settings=self.safety_settings,
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio="1:1",
                    image_size="1K",
                ),
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt, img_part],
                config=config,
            )

            if response.usage_metadata:
                logger.info(f"Usage metadata for slot machine icon:\n{response.usage_metadata}")

            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    image_bytes = ImageUtil.to_jpeg(image_bytes)
                    logger.info("Processing slot machine icon")
                    processed_image_bytes = ImageUtil.crop_to_content(image_bytes)
                    processed_image_bytes = ImageUtil.crop_to_aspect_ratio(processed_image_bytes, 1.0)

                    # Resize to target size (default 256x256) to reduce payload size
                    resized_image_bytes = ImageUtil.resize_to_dimensions(
                        processed_image_bytes, target_size, target_size,
                        output_format="JPEG",
                    )
                    logger.info(
                        f"Slot machine icon generated and resized to {target_size}x{target_size}."
                    )
                    return base64.b64encode(resized_image_bytes).decode("utf-8")

            logger.warning("No image data found in slot machine icon response.")
            return None
        except Exception as e:
            logger.error(f"Error generating slot machine icon: {e}")
            return None

    def generate_set_slot_icon(
        self,
        set_name: str,
        set_description: str | None = None,
        target_size: int = 256,
    ) -> str | None:
        """Generate a casino-styled slot icon for an aspect set from its theme.

        Unlike ``generate_slot_machine_icon`` which transforms a portrait image,
        this generates an icon purely from a text description of the set's theme.

        Args:
            set_name: The set's display name (used as the theme).
            set_description: Optional description for additional thematic context.
            target_size: Target size for the output icon (default 256×256).

        Returns:
            Base64-encoded 1:1 JPEG icon, or ``None`` on failure.
        """
        try:
            from settings.constants import SET_SLOT_ICON_PROMPT

            description_block = (
                f'Theme description: "{set_description}"'
                if set_description
                else "No additional description — infer imagery from the theme name."
            )
            prompt = SET_SLOT_ICON_PROMPT.format(
                set_name=set_name,
                description_block=description_block,
            )

            logger.info("Requesting set slot icon generation for set '%s'", set_name)

            config = types.GenerateContentConfig(
                safety_settings=self.safety_settings,
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio="1:1",
                    image_size="1K",
                ),
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt],
                config=config,
            )

            if response.usage_metadata:
                logger.info("Usage metadata for set slot icon:\n%s", response.usage_metadata)

            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    image_bytes = ImageUtil.to_jpeg(image_bytes)
                    processed_image_bytes = ImageUtil.crop_to_content(image_bytes)
                    processed_image_bytes = ImageUtil.crop_to_aspect_ratio(
                        processed_image_bytes, 1.0
                    )
                    resized_image_bytes = ImageUtil.resize_to_dimensions(
                        processed_image_bytes, target_size, target_size,
                        output_format="JPEG",
                    )
                    logger.info(
                        "Set slot icon for '%s' generated and resized to %dx%d.",
                        set_name,
                        target_size,
                        target_size,
                    )
                    return base64.b64encode(resized_image_bytes).decode("utf-8")

            logger.warning("No image data found in set slot icon response.")
            return None
        except Exception as e:
            logger.error("Error generating set slot icon for '%s': %s", set_name, e)
            return None

    def generate_aspect_image(
        self,
        aspect_name: str,
        rarity: str,
        set_name: str | None = None,
        set_description: str | None = None,
        type_name: str | None = None,
        type_description: str | None = None,
        temperature: float = 1.0,
        instruction_addendum: str = "",
    ) -> str | None:
        """Generate a 1:1 aspect sphere image from the sphere template.

        Args:
            aspect_name: The thematic name of the aspect (e.g. "Rainy").
            rarity: Rarity tier — used to look up creativeness_factor.
            set_name: Optional set name for thematic context.
            set_description: Optional set description for thematic context.
            type_name: Optional type name (e.g. "Location") for generation guidance.
            type_description: Optional type description for additional context.
            temperature: Gemini sampling temperature.
            instruction_addendum: Extra instructions appended to the prompt
                (e.g. user description for Unique creations).

        Returns:
            Base64-encoded 1:1 sphere image, or None on failure.
        """
        try:
            # Build set context
            if set_name:
                set_details = (
                    f"'{set_name}': {set_description}" if set_description else f"'{set_name}'"
                )
                set_context = ASPECT_SET_CONTEXT.format(set_details=set_details)
            else:
                set_context = ""

            # Build type context
            if type_name:
                type_details = (
                    f"'{type_name}': {type_description}" if type_description else f"'{type_name}'"
                )
                type_context = ASPECT_TYPE_CONTEXT.format(type_details=type_details)
            else:
                type_context = ""

            creativeness = RARITIES.get(rarity, {}).get("creativeness_factor", 50)
            color = RARITIES.get(rarity, {}).get("color", "blue")

            prompt = ASPECT_GENERATION_PROMPT.format(
                aspect_name=aspect_name,
                set_context=set_context,
                type_context=type_context,
                creativeness_factor=creativeness,
                color=color,
            )

            # Unique aspects always get the special addendum
            if rarity == "Unique":
                prompt += UNIQUE_ASPECT_ADDENDUM

            if instruction_addendum:
                prompt += instruction_addendum

            logger.info(
                f"Requesting aspect sphere generation for '{aspect_name}', "
                f"rarity '{rarity}', set '{set_name or 'none'}' (temperature {temperature})"
            )

            # Load the sphere template
            sphere_template_path = os.path.join(CARD_TEMPLATES_PATH, "aspect_sphere.png")
            template_part = self._prepare_image_part(image_path=sphere_template_path)

            config = types.GenerateContentConfig(
                temperature=temperature,
                safety_settings=self.safety_settings,
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio="1:1",
                    image_size="1K",
                ),
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt, template_part],
                config=config,
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    image_bytes = ImageUtil.to_jpeg(image_bytes)
                    # Crop borders, then force 1:1 square
                    processed = ImageUtil.crop_to_content(image_bytes)
                    processed = ImageUtil.crop_to_aspect_ratio(processed, 1.0)
                    logger.info(
                        f"Aspect sphere for '{aspect_name}' generated and processed successfully."
                    )
                    return base64.b64encode(processed).decode("utf-8")

            logger.warning("No image data found in aspect sphere response.")
            return None
        except Exception as e:
            logger.error(f"Error generating aspect sphere image: {e}")
            return None

    def generate_card_with_aspects(
        self,
        rarity: str,
        card_name: str,
        aspects: list,
        base_image_path: str | None = None,
        base_image_b64: str | None = None,
        temperature: float = 1.0,
    ) -> str | None:
        """Generate a card image from scratch with equipped aspects.

        Uses the character photo, rarity template, and all equipped aspect
        sphere images to produce a fresh card. Used by both /equip and /refresh.

        Args:
            rarity: Card rarity (for template selection, color, creativeness).
            card_name: Full display name for the card nameplate.
            aspects: List of OwnedAspectWithImage objects for ALL equipped aspects.
            base_image_path: Path to the character's base photo.
            base_image_b64: Base64-encoded character base photo.
            temperature: Gemini sampling temperature.

        Returns:
            Base64-encoded card image, or None on failure.
        """
        try:
            if base_image_path is None and base_image_b64 is None:
                raise ValueError("Either base_image_path or base_image_b64 must be provided.")

            # Build rich per-aspect descriptions with set and type context
            if aspects:
                aspect_labels = []
                for a in aspects:
                    if a.aspect_definition:
                        aspect_labels.append(a.aspect_definition.context_label())
                    else:
                        aspect_labels.append(f'"{a.display_name}"')
                aspects_desc = "; ".join(aspect_labels)
            else:
                aspects_desc = "None"

            prompt = CARD_WITH_ASPECTS_PROMPT.format(
                card_name=card_name,
                aspects=aspects_desc,
                rarity=rarity,
                color=RARITIES[rarity]["color"],
                creativeness_factor=RARITIES[rarity]["creativeness_factor"],
            )

            logger.info(
                f"Requesting card-with-aspects generation for '{card_name}', "
                f"rarity '{rarity}', {len(aspects)} aspects (temperature {temperature})"
            )

            # Prepare image parts: rarity template + character photo + labeled aspect references
            template_image_path = os.path.join(CARD_TEMPLATES_PATH, f"{rarity.lower()}.png")
            contents: list = [prompt]
            contents.append("Card template:")
            contents.append(self._prepare_image_part(image_path=template_image_path))
            contents.append("Character photo:")
            contents.append(
                self._prepare_image_part(image_path=base_image_path, image_b64=base_image_b64)
            )
            for a in aspects:
                label = f'Aspect {a.aspect_definition.context_label(include_descriptions=False) if a.aspect_definition else f"{a.display_name}"}'
                contents.append(f'{label} reference:')
                contents.append(self._prepare_image_part(image_bytes=base64.b64decode(a.image_b64)))

            config = types.GenerateContentConfig(
                temperature=temperature,
                safety_settings=self.safety_settings,
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(image_size="1K"),
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    image_bytes = ImageUtil.to_jpeg(image_bytes)
                    processed = ImageUtil.crop_to_content(image_bytes)
                    processed = ImageUtil.crop_to_aspect_ratio(processed, 5/7)
                    logger.info(f"Card-with-aspects image for '{card_name}' generated successfully.")
                    return base64.b64encode(processed).decode("utf-8")

            logger.warning("No image data found in card-with-aspects generation response.")
            return None
        except Exception as e:
            logger.error(f"Error generating card-with-aspects image: {e}")
            return None
