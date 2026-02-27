import base64
import logging
import os
import random
from io import BytesIO

from google import genai
from google.genai import types
from PIL import Image

from settings.constants import (
    IMAGE_GENERATOR_INSTRUCTION,
    RARITIES,
    CARD_TEMPLATES_PATH,
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
    ):
        try:
            if base_image_path is None and base_image_b64 is None:
                raise ValueError("Either base_image_path or base_image_b64 must be provided.")

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
