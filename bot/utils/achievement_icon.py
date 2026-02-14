"""Shared utilities for generating achievement icons using Gemini AI."""

from __future__ import annotations

import base64
import logging
from io import BytesIO
from pathlib import Path

from PIL import Image

from config import GOOGLE_API_KEY, IMAGE_GEN_MODEL
from utils.image import ImageUtil

logger = logging.getLogger(__name__)

# Achievement icon generation prompt
ACHIEVEMENT_ICON_PROMPT = """Generate a circular achievement badge icon for a game.

Achievement Name: {name}
Achievement Description: {description}

Requirements:
- The icon should be a circular badge/medallion design
- Use bold, vibrant colors that stand out
- Include visual elements that represent the achievement theme
- The design should be clean and recognizable at small sizes
- Add subtle metallic or glossy effects for a premium feel
- Include a decorative border around the circle
- The overall style should be similar to gaming achievement icons
- Do NOT include any text in the icon
- The background should be transparent or a solid dark color

Generate a single circular achievement badge icon that visually represents this accomplishment."""


def generate_achievement_icon(name: str, description: str) -> str | None:
    """
    Generate an achievement icon using Gemini AI.

    Args:
        name: The achievement name.
        description: The achievement description.

    Returns:
        Base64-encoded PNG image, or None if generation failed.
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GOOGLE_API_KEY)

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

        prompt = ACHIEVEMENT_ICON_PROMPT.format(name=name, description=description)
        logger.info("Generating achievement icon for '%s'...", name)

        config = types.GenerateContentConfig(safety_settings=safety_settings)
        response = client.models.generate_content(
            model=IMAGE_GEN_MODEL,
            contents=[prompt],
            config=config,
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data:
                image_bytes = part.inline_data.data
                logger.info("Raw image generated, processing...")

                # Crop to content (remove any borders/whitespace)
                processed_bytes = ImageUtil.crop_to_content(image_bytes)

                # Resize to 256x256
                resized_bytes = ImageUtil.resize_to_dimensions(processed_bytes, 256, 256)

                logger.info("Icon processed and resized to 256x256")
                return base64.b64encode(resized_bytes).decode("utf-8")

        logger.warning("No image data in Gemini response")
        return None

    except Exception as e:
        logger.error("Failed to generate achievement icon: %s", e, exc_info=True)
        return None


def save_icon_preview(icon_b64: str, name: str, output_dir: Path) -> Path:
    """
    Save a preview of the icon to the specified directory.

    Args:
        icon_b64: Base64-encoded PNG image.
        name: Achievement name (used for filename).
        output_dir: Directory to save the preview.

    Returns:
        Path to the saved file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"achievement_{name.lower().replace(' ', '_')}.png"

    image_bytes = base64.b64decode(icon_b64)
    img = Image.open(BytesIO(image_bytes))
    img.save(output_path, "PNG")

    logger.info("Preview saved to: %s", output_path)
    return output_path
