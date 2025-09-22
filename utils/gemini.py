import base64
import logging
import os

import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image

from settings.constants import IMAGE_GENERATOR_INSTRUCTION, RARITIES, CARD_TEMPLATES_PATH
from utils.image import ImageUtil

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
                creativeness_factor=RARITIES[rarity]["creativeness_factor"],
            )
            logger.info(
                f"Requesting image generation for '{base_name}' with modifier '{modifier}' and rarity '{rarity}'"
            )
            template_image_path = os.path.join(CARD_TEMPLATES_PATH, f"{rarity.lower()}.png")
            template_img = Image.open(template_image_path)
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
