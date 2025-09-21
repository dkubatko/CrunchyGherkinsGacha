import base64
import io
import logging
import os

import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image

from settings.constants import IMAGE_GENERATOR_INSTRUCTION, RARITIES

load_dotenv()

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

logger = logging.getLogger(__name__)


class GeminiUtil:
    def __init__(self):
        self.model = genai.GenerativeModel(os.getenv("IMAGE_GEN_MODEL"))

    def generate_image(
        self,
        base_name: str,
        modifier: str,
        rarity: str,
        base_image_path: str,
    ):
        try:
            prompt = IMAGE_GENERATOR_INSTRUCTION.format(
                modification=modifier,
                name=base_name,
                rarity=rarity,
                color=RARITIES[rarity]["color"],
            )
            logger.info(
                f"Requesting image generation for '{base_name}' with modifier '{modifier}' and rarity '{rarity}'"
            )
            img = Image.open(base_image_path)
            response = self.model.generate_content([prompt, img])

            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    logger.info("Image generated successfully.")
                    return base64.b64encode(image_bytes).decode("utf-8")
            logger.warning("No image data found in response.")
            return None
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return None
