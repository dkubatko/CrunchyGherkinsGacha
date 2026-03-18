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
    BASE_CARD_GENERATION_PROMPT,
    EQUIP_GENERATION_PROMPT,
    IMAGE_GENERATOR_INSTRUCTION,
    RARITIES,
    CARD_TEMPLATES_PATH,
    REFRESH_EQUIPPED_PROMPT,
    SLOT_MACHINE_INSTRUCTION,
    SET_CONTEXT,
)
from utils.image import ImageUtil
from utils.schemas import Modifier

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
        modifier: str,
        rarity: str,
        base_image_path: str | None = None,
        base_image_b64: str | None = None,
        temperature: float = 1.0,
        instruction_addendum: str = "",
        modifier_info: Modifier | None = None,
        no_modifier: bool = False,
    ):
        try:
            if base_image_path is None and base_image_b64 is None:
                raise ValueError("Either base_image_path or base_image_b64 must be provided.")

            if no_modifier:
                # Base card generation — no modifier/modification applied
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
            else:
                # Extract set context from modifier_info if available
                set_name = modifier_info.set_name if modifier_info else ""
                set_description = modifier_info.description if modifier_info else ""

                # Build conditional set context if set_name is provided
                if set_name:
                    set_details = (
                        f"'{set_name}': {set_description}" if set_description else f"'{set_name}'"
                    )
                    set_context = SET_CONTEXT.format(set_details=set_details)
                else:
                    set_context = ""

                prompt = IMAGE_GENERATOR_INSTRUCTION.format(
                    modification=modifier,
                    name=base_name,
                    rarity=rarity,
                    color=RARITIES[rarity]["color"],
                    creativeness_factor=RARITIES[rarity]["creativeness_factor"],
                    set_context=set_context,
                )
                if instruction_addendum:
                    prompt += instruction_addendum

                logger.info(
                    f"Requesting image generation for '{base_name}' with modifier '{modifier}', rarity '{rarity}', set '{set_name or 'none'}' (temperature {temperature})"
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
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt, template_part, img_part],
                config=config,
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    processed_image_bytes = ImageUtil.crop_to_content(image_bytes)
                    logger.info(
                        f"Image for {modifier} {base_name} generated and processed successfully."
                    )
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
                    logger.info("Processing slot machine icon")
                    processed_image_bytes = ImageUtil.crop_to_content(image_bytes)

                    # Resize to target size (default 256x256) to reduce payload size
                    resized_image_bytes = ImageUtil.resize_to_dimensions(
                        processed_image_bytes, target_size, target_size
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

    def generate_aspect_image(
        self,
        aspect_name: str,
        rarity: str,
        set_name: str | None = None,
        set_description: str | None = None,
        temperature: float = 1.0,
    ) -> str | None:
        """Generate a 1:1 aspect sphere image from the sphere template.

        Args:
            aspect_name: The thematic name of the aspect (e.g. "Rainy").
            rarity: Rarity tier — used to look up creativeness_factor.
            set_name: Optional set name for thematic context.
            set_description: Optional set description for thematic context.
            temperature: Gemini sampling temperature.

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

            creativeness = RARITIES.get(rarity, {}).get("creativeness_factor", 50)

            prompt = ASPECT_GENERATION_PROMPT.format(
                aspect_name=aspect_name,
                set_context=set_context,
                creativeness_factor=creativeness,
            )

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
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt, template_part],
                config=config,
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    # Crop borders, then force 1:1 square
                    processed = ImageUtil.crop_to_content(image_bytes)
                    processed = ImageUtil.crop_to_square(processed)
                    logger.info(
                        f"Aspect sphere for '{aspect_name}' generated and processed successfully."
                    )
                    return base64.b64encode(processed).decode("utf-8")

            logger.warning("No image data found in aspect sphere response.")
            return None
        except Exception as e:
            logger.error(f"Error generating aspect sphere image: {e}")
            return None

    def generate_equipped_card_image(
        self,
        card_image_b64: str,
        existing_aspects: list[tuple[str, bytes]],
        new_aspect_name: str,
        new_aspect_image_bytes: bytes,
        rarity: str,
        card_name: str,
        temperature: float = 1.0,
    ) -> str | None:
        """Generate a transformed card image by applying a new aspect.

        Sends the current card image plus all aspect sphere images to Gemini,
        which produces a new card image that visually incorporates the new
        aspect theme while preserving previously applied aspects.

        Args:
            card_image_b64: Base64-encoded current card image.
            existing_aspects: List of (name, image_bytes) for previously equipped aspects.
            new_aspect_name: Name of the aspect being equipped now.
            new_aspect_image_bytes: Raw bytes of the new aspect's sphere image.
            rarity: Card rarity (for color and creativeness lookup).
            card_name: Full display name for the card nameplate.
            temperature: Gemini sampling temperature.

        Returns:
            Base64-encoded transformed card image, or None on failure.
        """
        try:
            # Build existing aspects description
            if existing_aspects:
                existing_desc = ", ".join(f'"{name}"' for name, _ in existing_aspects)
            else:
                existing_desc = "None (this is the first aspect being applied)"

            prompt = EQUIP_GENERATION_PROMPT.format(
                card_name=card_name,
                existing_aspects=existing_desc,
                new_aspect_name=new_aspect_name,
                rarity=rarity,
                color=RARITIES[rarity]["color"],
                creativeness_factor=RARITIES[rarity]["creativeness_factor"],
            )

            logger.info(
                f"Requesting equip card generation for '{card_name}', "
                f"new aspect '{new_aspect_name}', rarity '{rarity}' "
                f"({len(existing_aspects)} existing aspects) (temperature {temperature})"
            )

            # Prepare image parts: current card + existing aspect spheres + new aspect sphere
            contents: list = [prompt]
            contents.append(self._prepare_image_part(image_b64=card_image_b64))
            for aspect_name, aspect_bytes in existing_aspects:
                contents.append(self._prepare_image_part(image_bytes=aspect_bytes))
            contents.append(self._prepare_image_part(image_bytes=new_aspect_image_bytes))

            config = types.GenerateContentConfig(
                temperature=temperature,
                safety_settings=self.safety_settings,
                response_modalities=["IMAGE"],
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    processed = ImageUtil.crop_to_content(image_bytes)
                    logger.info(f"Equipped card image for '{card_name}' generated successfully.")
                    return base64.b64encode(processed).decode("utf-8")

            logger.warning("No image data found in equip card generation response.")
            return None
        except Exception as e:
            logger.error(f"Error generating equipped card image: {e}")
            return None

    def generate_refresh_equipped_image(
        self,
        rarity: str,
        card_name: str,
        aspects: list[tuple[str, bytes]],
        base_image_path: str | None = None,
        base_image_b64: str | None = None,
        temperature: float = 1.0,
    ) -> str | None:
        """Generate a completely fresh card image for a card with equipped aspects.

        Unlike generate_equipped_card_image, this does NOT use the existing card
        image. Instead it starts from scratch with the character photo, the
        rarity template, and all equipped aspect sphere images.

        Args:
            rarity: Card rarity (for template selection, color, creativeness).
            card_name: Full display name for the card nameplate.
            aspects: List of (name, image_bytes) for ALL equipped aspects.
            base_image_path: Path to the character's base photo.
            base_image_b64: Base64-encoded character base photo.
            temperature: Gemini sampling temperature.

        Returns:
            Base64-encoded fresh card image, or None on failure.
        """
        try:
            if base_image_path is None and base_image_b64 is None:
                raise ValueError("Either base_image_path or base_image_b64 must be provided.")

            # Build aspects description
            if aspects:
                aspects_desc = ", ".join(f'"{name}"' for name, _ in aspects)
            else:
                aspects_desc = "None"

            prompt = REFRESH_EQUIPPED_PROMPT.format(
                card_name=card_name,
                aspects=aspects_desc,
                rarity=rarity,
                color=RARITIES[rarity]["color"],
                creativeness_factor=RARITIES[rarity]["creativeness_factor"],
            )

            logger.info(
                f"Requesting refresh-equipped generation for '{card_name}', "
                f"rarity '{rarity}', {len(aspects)} aspects (temperature {temperature})"
            )

            # Prepare image parts: rarity template + character photo + aspect spheres
            template_image_path = os.path.join(CARD_TEMPLATES_PATH, f"{rarity.lower()}.png")
            contents: list = [prompt]
            contents.append(self._prepare_image_part(image_path=template_image_path))
            contents.append(
                self._prepare_image_part(image_path=base_image_path, image_b64=base_image_b64)
            )
            for aspect_name, aspect_bytes in aspects:
                contents.append(self._prepare_image_part(image_bytes=aspect_bytes))

            config = types.GenerateContentConfig(
                temperature=temperature,
                safety_settings=self.safety_settings,
                response_modalities=["IMAGE"],
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    processed = ImageUtil.crop_to_content(image_bytes)
                    logger.info(f"Refresh-equipped image for '{card_name}' generated successfully.")
                    return base64.b64encode(processed).decode("utf-8")

            logger.warning("No image data found in refresh-equipped generation response.")
            return None
        except Exception as e:
            logger.error(f"Error generating refresh-equipped image: {e}")
            return None
