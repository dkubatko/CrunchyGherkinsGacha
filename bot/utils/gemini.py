import base64
import logging
import os
import random
from io import BytesIO

import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image

from settings.constants import (
    IMAGE_GENERATOR_INSTRUCTION,
    RARITIES,
    CARD_TEMPLATES_PATH,
    SLOT_MACHINE_INSTRUCTION,
)
from utils.image import ImageUtil

load_dotenv()

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
logger = logging.getLogger(__name__)


class GeminiUtil:
    def __init__(self):
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
        self.model = genai.GenerativeModel(
            os.getenv("IMAGE_GEN_MODEL"), safety_settings=safety_settings
        )

    def generate_image(
        self,
        base_name: str,
        modifier: str,
        rarity: str,
        base_image_path: str | None = None,
        base_image_b64: str | None = None,
    ):
        try:
            if base_image_path is None and base_image_b64 is None:
                raise ValueError("Either base_image_path or base_image_b64 must be provided.")

            prompt = IMAGE_GENERATOR_INSTRUCTION.format(
                modification=modifier,
                name=base_name,
                rarity=rarity,
                color=RARITIES[rarity]["color"],
                creativeness_factor=RARITIES[rarity]["creativeness_factor"],
            )
            logger.info(
                f"Requesting image generation for '{base_name}' with modifier '{modifier}' and rarity '{rarity}'"
            )
            template_image_path = os.path.join(CARD_TEMPLATES_PATH, f"{rarity.lower()}.png")
            template_img = Image.open(template_image_path)
            if base_image_b64:
                source_bytes = base64.b64decode(base_image_b64)
                img = Image.open(BytesIO(source_bytes))
            else:
                img = Image.open(base_image_path)
            response = self.model.generate_content([prompt, template_img, img])

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
    ):
        """Generate a 1:1 aspect ratio slot machine icon from a user's image."""
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

            response = self.model.generate_content([prompt, img])

            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    logger.info("Processing slot machine icon")
                    processed_image_bytes = ImageUtil.crop_to_content(image_bytes)
                    logger.info("Slot machine icon generated and processed successfully.")
                    return base64.b64encode(processed_image_bytes).decode("utf-8")

            logger.warning("No image data found in slot machine icon response.")
            return None
        except Exception as e:
            logger.error(f"Error generating slot machine icon: {e}")
            return None
