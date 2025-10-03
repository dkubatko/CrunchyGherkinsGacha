"""
One-time script to generate a Claim point icon using Gemini.
Generates a casino-themed icon with the letter "C" in the middle.
"""

import base64
import logging
import os
import sys
from io import BytesIO

import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image

# Add parent directory to path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.image import ImageUtil

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

CLAIM_ICON_INSTRUCTION = """
Generate a casino-themed icon with the letter "C" prominently displayed in the middle.

Style requirements:
- 1:1 aspect ratio (square icon)
- Casino/slot machine aesthetic with vibrant colors
- Bold, eye-catching letter "C" as the centerpiece
- Clean, modern design - avoid excessive details or clutter
- Subtle casino elements (like a simple gold border or soft glow effect)
- The "C" should be clearly readable and stand out
- High contrast and visual appeal suitable for a game interface
- Professional quality with clean edges
- IMPORTANT: Only the letter "C" should appear - no other text, words, or labels
- Keep it sleek and minimalistic while maintaining the exciting casino vibe
"""


def generate_claim_icon(output_path: str):
    """Generate a claim icon and save it to the specified path."""
    try:
        # Configure safety settings
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

        model = genai.GenerativeModel(os.getenv("IMAGE_GEN_MODEL"), safety_settings=safety_settings)

        logger.info("Requesting claim icon generation from Gemini...")
        response = model.generate_content([CLAIM_ICON_INSTRUCTION])

        for part in response.candidates[0].content.parts:
            if part.inline_data:
                image_bytes = part.inline_data.data
                logger.info("Processing claim icon...")
                processed_image_bytes = ImageUtil.crop_to_content(image_bytes)

                # Save the image
                with open(output_path, "wb") as f:
                    f.write(processed_image_bytes)

                logger.info(f"Claim icon generated and saved to: {output_path}")

                # Also save as base64 for easy database insertion
                base64_str = base64.b64encode(processed_image_bytes).decode("utf-8")
                base64_output_path = output_path.replace(".png", "_b64.txt")
                with open(base64_output_path, "w") as f:
                    f.write(base64_str)
                logger.info(f"Base64 version saved to: {base64_output_path}")

                return processed_image_bytes

        logger.warning("No image data found in response.")
        return None

    except Exception as e:
        logger.error(f"Error generating claim icon: {e}")
        return None


if __name__ == "__main__":
    # Configure Gemini API
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not found in environment variables")
        sys.exit(1)

    genai.configure(api_key=api_key)

    # Set output path
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "slots"
    )
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "claim_icon.png")

    logger.info("Starting claim icon generation...")
    result = generate_claim_icon(output_path)

    if result:
        logger.info("✅ Claim icon generation completed successfully!")
    else:
        logger.error("❌ Failed to generate claim icon")
        sys.exit(1)
