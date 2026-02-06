import base64
import logging
import os
import random
from io import BytesIO

import google.generativeai as genai
from PIL import Image

from settings.constants import (
    GEMINI_TIMEOUT_SECONDS,
    IMAGE_GENERATOR_INSTRUCTION,
    RARITIES,
    CARD_TEMPLATES_PATH,
    SLOT_MACHINE_INSTRUCTION,
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
        genai.configure(api_key=google_api_key)

        # Configure safety settings to be least restrictive
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_NONE",
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_NONE",
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_NONE",
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_NONE",
            },
        ]
        self.model = genai.GenerativeModel(image_gen_model, safety_settings=safety_settings)
        logger.info(f"GeminiUtil initialized with model {image_gen_model}")

    def generate_image(
        self,
        base_name: str,
        modifier: str,
        rarity: str,
        base_image_path: str | None = None,
        base_image_b64: str | None = None,
        temperature: float = 1.0,
        instruction_addendum: str = "",
        set_name: str = "",
    ):
        try:
            if base_image_path is None and base_image_b64 is None:
                raise ValueError("Either base_image_path or base_image_b64 must be provided.")

            # Build conditional set context if set_name is provided
            set_context = (
                f'The modifier is part of a themed set called **"{set_name}"**; interpret it within that theme.'
                if set_name
                else ""
            )

            prompt = IMAGE_GENERATOR_INSTRUCTION.format(
                modification=modifier,
                name=base_name,
                rarity=rarity,
                color=RARITIES[rarity]["color"],
                creativeness_factor=RARITIES[rarity]["creativeness_factor"],
                set_context=set_context,
            )
            if instruction_addendum:
                prompt += "\n" + instruction_addendum

            logger.info(
                f"Requesting image generation for '{base_name}' with modifier '{modifier}', rarity '{rarity}', set '{set_name or 'none'}' (temperature {temperature})"
            )

            generation_config = genai.types.GenerationConfig(temperature=temperature)

            template_image_path = os.path.join(CARD_TEMPLATES_PATH, f"{rarity.lower()}.png")
            template_img = Image.open(template_image_path)
            if base_image_b64:
                source_bytes = base64.b64decode(base_image_b64)
                img = Image.open(BytesIO(source_bytes))
            else:
                img = Image.open(base_image_path)
            response = self.model.generate_content(
                [prompt, template_img, img],
                generation_config=generation_config,
                request_options={"timeout": GEMINI_TIMEOUT_SECONDS},
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    logger.info(f"Cropping image {modifier} {base_name}")
                    processed_image_bytes = ImageUtil.crop_to_content(image_bytes)
                    logger.info("Image generated and processed successfully.")
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
            img = Image.open(BytesIO(square_image_bytes))

            response = self.model.generate_content(
                [prompt, img],
                request_options={"timeout": GEMINI_TIMEOUT_SECONDS},
            )

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
