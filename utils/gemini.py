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

    def _remove_background(self, image_bytes: bytes) -> bytes:
        """
        Removes the white and black borders from an image by cropping it.
        """
        try:
            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_bytes))

            # Convert to RGB if not already (to handle RGBA, etc.)
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Define white and black color thresholds
            white_threshold = 240  # Pixels with all RGB values >= 240 are considered white
            black_threshold = 15  # Pixels with all RGB values <= 15 are considered black

            # Get image dimensions
            width, height = image.size

            # Find the bounding box of content that's neither white nor black
            left = width
            top = height
            right = 0
            bottom = 0

            # Scan all pixels to find the bounds of non-white and non-black content
            pixels = image.load()
            for y in range(height):
                for x in range(width):
                    r, g, b = pixels[x, y]
                    # Check if pixel is neither white nor black
                    is_white = (
                        r >= white_threshold and g >= white_threshold and b >= white_threshold
                    )
                    is_black = (
                        r <= black_threshold and g <= black_threshold and b <= black_threshold
                    )

                    # If pixel is neither white nor black, include it in bounding box
                    if not is_white and not is_black:
                        left = min(left, x)
                        right = max(right, x)
                        top = min(top, y)
                        bottom = max(bottom, y)

            # If no content found (only white/black pixels), return original image
            if left >= right or top >= bottom:
                logger.warning(
                    "No content found (only white/black pixels) in image, returning original"
                )
                return image_bytes

            # Crop the image to the bounding box
            cropped_image = image.crop((left, top, right + 1, bottom + 1))

            # Convert back to bytes
            output_buffer = io.BytesIO()
            cropped_image.save(output_buffer, format="PNG")
            processed_bytes = output_buffer.getvalue()

            logger.info(
                f"White and black background removed. Original size: {width}x{height}, Cropped size: {cropped_image.size[0]}x{cropped_image.size[1]}"
            )
            return processed_bytes

        except Exception as e:
            logger.error(f"Error removing white and black background: {e}")
            # Return original image bytes if processing fails
            return image_bytes

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
            template_image_path = f"data/card_templates/{rarity.lower()}.png"
            template_img = Image.open(template_image_path)
            img = Image.open(base_image_path)
            response = self.model.generate_content([prompt, template_img, img])

            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    processed_image_bytes = self._remove_background(image_bytes)
                    logger.info("Image generated and processed successfully.")
                    return base64.b64encode(processed_image_bytes).decode("utf-8")
            logger.warning("No image data found in response.")
            return None
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return None
