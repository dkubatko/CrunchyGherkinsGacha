"""
One-time script to generate a Mine/Bomb icon for minesweeper using Gemini.
Generates a bomb/mine icon suitable for the minesweeper game.
"""

import base64
import logging
import os
import sys
from io import BytesIO

from google import genai
from google.genai import types
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

MINE_ICON_INSTRUCTION = """
Generate a bomb/mine icon for a minesweeper game with a prominent bomb emoji-style design.

Style requirements:
- 1:1 aspect ratio with a ROUND/CIRCULAR shape (like a classic cartoon bomb)
- Dark background (black or very dark gray) around the circular icon
- Classic bomb aesthetic - think classic round black bomb with a lit fuse
- Bold, eye-catching bomb design as the centerpiece
- Clean, modern design - avoid excessive details or clutter
- Circular shape overall (the bomb itself should be round)
- The icon should be round with no square corners
- Use a classic color scheme: black bomb body, orange/yellow flame on fuse
- The bomb should be clearly identifiable and stand out
- High contrast and visual appeal suitable for a game interface
- Professional quality with smooth circular edges
- IMPORTANT: No text, letters, words, or labels should appear
- IMPORTANT: The background outside the circular icon should be dark (black or very dark gray), not white
- Keep it sleek and minimalistic while maintaining the dangerous/explosive vibe
- Think of it as a classic cartoon bomb icon on a dark background
- The design should evoke "danger" or "explosive" but in a playful, game-appropriate way
- Consider including a small lit fuse with a spark/flame for visual interest
- The bomb should feel threatening but not realistic/graphic - keep it game-friendly
"""


def generate_mine_icon(client, output_path: str):
    """Generate a mine/bomb icon and save it to the specified path."""
    try:
        # Configure safety settings
        safety_settings = [
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

        config = types.GenerateContentConfig(safety_settings=safety_settings)

        logger.info("Requesting mine icon generation from Gemini...")
        response = client.models.generate_content(
            model=os.getenv("IMAGE_GEN_MODEL"),
            contents=[MINE_ICON_INSTRUCTION],
            config=config,
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data:
                image_bytes = part.inline_data.data
                logger.info("Saving mine icon (no cropping)...")

                # Save the image directly without cropping
                with open(output_path, "wb") as f:
                    f.write(image_bytes)

                logger.info(f"Mine icon generated and saved to: {output_path}")

                return image_bytes

        logger.warning("No image data found in response.")
        return None

    except Exception as e:
        logger.error(f"Error generating mine icon: {e}")
        return None


if __name__ == "__main__":
    # Configure Gemini API
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not found in environment variables")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    # Set output path - save to data/minesweeper directory
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "minesweeper"
    )
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "mine_icon.png")

    logger.info("Starting mine icon generation...")
    result = generate_mine_icon(client, output_path)

    if result:
        logger.info("✅ Mine icon generation completed successfully!")
    else:
        logger.error("❌ Failed to generate mine icon")
        sys.exit(1)
