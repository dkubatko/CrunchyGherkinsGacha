"""Export all card images for a specific season as PNGs with rounded corners.

Usage:
    python tools/export_season_images.py <season_id> [--count N]

Example:
    python tools/export_season_images.py 0
    python tools/export_season_images.py 1 --count 50

This will:
1. Query cards for the given season from the most common chat_id
2. Process each card image to:
   - Resize to 5:7 aspect ratio (1024x1434)
   - Apply rounded corners matching the miniapp border-radius
3. Save each image as PNG to data/output/
4. Create a zip archive: season_{season_id}_images.zip

Options:
    --count N    Limit export to N cards (optional, exports all by default)
"""

from __future__ import annotations

import argparse
import base64
import io
import logging
import os
import shutil
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw
from sqlalchemy import func

# Ensure project root is on sys.path for module imports
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

from utils.session import get_session  # noqa: E402
from utils.models import CardModel, CardImageModel  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Output dimensions matching 5:7 aspect ratio (width:height)
OUTPUT_WIDTH = 1024
OUTPUT_HEIGHT = int(OUTPUT_WIDTH * (7 / 5))  # 1434

# Border radius for the miniapp cards (25px at display size)
# Scale proportionally for the output resolution
# The miniapp displays cards at roughly 300-400px width with 25px border radius
# For 1024px width, scale proportionally: 25 * (1024 / 350) ≈ 73px
DISPLAY_WIDTH_APPROX = 350
BORDER_RADIUS = int(25 * (OUTPUT_WIDTH / DISPLAY_WIDTH_APPROX))


def get_most_common_chat_id() -> str:
    """Get the most common chat_id from the cards table."""
    with get_session() as session:
        result = (
            session.query(CardModel.chat_id, func.count(CardModel.chat_id).label("count"))
            .filter(CardModel.chat_id.isnot(None))
            .group_by(CardModel.chat_id)
            .order_by(func.count(CardModel.chat_id).desc())
            .first()
        )

        if result is None:
            raise RuntimeError("No cards with chat_id found in the database")

        return result[0]


def create_rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    """Create a rounded rectangle mask for the given size.

    Args:
        size: Tuple of (width, height) for the mask
        radius: Corner radius in pixels

    Returns:
        PIL Image mask with rounded corners
    """
    width, height = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)

    # Draw a rounded rectangle
    draw.rounded_rectangle([(0, 0), (width - 1, height - 1)], radius=radius, fill=255)

    return mask


def process_image(image_b64: str) -> Image.Image:
    """Process a base64 encoded image to the target format.

    Args:
        image_b64: Base64 encoded image string

    Returns:
        Processed PIL Image with rounded corners
    """
    # Decode base64 to image
    image_data = base64.b64decode(image_b64)
    image = Image.open(io.BytesIO(image_data))

    # Convert to RGBA if not already (for transparency support)
    if image.mode != "RGBA":
        image = image.convert("RGBA")

    # Calculate dimensions for 5:7 aspect ratio crop/fit
    orig_width, orig_height = image.size
    target_ratio = 5 / 7  # width / height
    orig_ratio = orig_width / orig_height

    if orig_ratio > target_ratio:
        # Image is wider than target, crop sides
        new_width = int(orig_height * target_ratio)
        left = (orig_width - new_width) // 2
        image = image.crop((left, 0, left + new_width, orig_height))
    elif orig_ratio < target_ratio:
        # Image is taller than target, crop top/bottom
        new_height = int(orig_width / target_ratio)
        top = (orig_height - new_height) // 2
        image = image.crop((0, top, orig_width, top + new_height))

    # Resize to target dimensions
    image = image.resize((OUTPUT_WIDTH, OUTPUT_HEIGHT), Image.Resampling.LANCZOS)

    # Create rounded corner mask
    mask = create_rounded_mask((OUTPUT_WIDTH, OUTPUT_HEIGHT), BORDER_RADIUS)

    # Apply mask to create transparent corners
    # Create new image with transparency
    output = Image.new("RGBA", (OUTPUT_WIDTH, OUTPUT_HEIGHT), (0, 0, 0, 0))
    output.paste(image, (0, 0), mask)

    return output


def export_season_images(season_id: int, count: int | None = None) -> None:
    """Export all card images for a specific season.

    Args:
        season_id: The season ID to export cards for
        count: Maximum number of cards to export (None for all)
    """
    output_dir = PROJECT_ROOT / "data" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create temp directory for this export
    export_dir = output_dir / f"season_{season_id}_images"
    if export_dir.exists():
        shutil.rmtree(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    # Get the most common chat_id
    chat_id = get_most_common_chat_id()
    logger.info(f"Using most common chat_id: {chat_id}")

    logger.info(f"Exporting cards for season {season_id} to {export_dir}")

    with get_session() as session:
        # Query cards for the given season from the most common chat_id
        query = session.query(CardModel).filter(
            CardModel.season_id == season_id, CardModel.chat_id == chat_id
        )

        if count is not None:
            query = query.limit(count)

        cards = query.all()

        if not cards:
            logger.warning(f"No cards found for season {season_id}")
            return

        logger.info(f"Found {len(cards)} cards for season {season_id}")

        # Get card IDs
        card_ids = [card.id for card in cards]

        # Query all card images at once
        card_images = (
            session.query(CardImageModel).filter(CardImageModel.card_id.in_(card_ids)).all()
        )

        # Create lookup dict
        image_lookup = {img.card_id: img.image_b64 for img in card_images if img.image_b64}

        logger.info(f"Found {len(image_lookup)} cards with images")

        exported = 0
        skipped = 0

        for card in cards:
            image_b64 = image_lookup.get(card.id)

            if not image_b64:
                logger.warning(f"Card {card.id} ({card.base_name} - {card.modifier}) has no image")
                skipped += 1
                continue

            try:
                # Process the image
                processed = process_image(image_b64)

                # Create filename: <rarity>_<owner_username>_<card_id>_<modifier>_<name>.png
                # Sanitize filename components
                safe_rarity = "".join(c if c.isalnum() or c in " -_" else "_" for c in card.rarity)
                safe_owner = "".join(
                    c if c.isalnum() or c in " -_" else "_" for c in (card.owner or "unowned")
                )
                safe_modifier = "".join(
                    c if c.isalnum() or c in " -_" else "_" for c in card.modifier
                )
                safe_basename = "".join(
                    c if c.isalnum() or c in " -_" else "_" for c in card.base_name
                )

                filename = (
                    f"{safe_rarity}_{safe_owner}_{card.id}_{safe_modifier}_{safe_basename}.png"
                )
                filepath = export_dir / filename

                # Save as PNG
                processed.save(filepath, "PNG")
                exported += 1

                if exported % 10 == 0:
                    logger.info(f"Exported {exported}/{len(cards)} cards...")

            except Exception as e:
                logger.error(f"Failed to process card {card.id}: {e}")
                skipped += 1

    logger.info(f"Exported {exported} cards, skipped {skipped}")

    # Create zip archive
    zip_path = output_dir / f"season_{season_id}_images.zip"
    logger.info(f"Creating zip archive: {zip_path}")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in export_dir.iterdir():
            if file.is_file() and file.suffix == ".png":
                zipf.write(file, file.name)

    # Calculate zip size
    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    logger.info(f"Zip archive created: {zip_path} ({zip_size_mb:.2f} MB)")

    # Optionally clean up the temporary export directory
    # Keeping it for now so users can inspect individual files
    logger.info(f"Individual images saved in: {export_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export all card images for a specific season as PNGs with rounded corners"
    )
    parser.add_argument("season_id", type=int, help="The season ID to export cards for")
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Maximum number of cards to export (optional, exports all by default)",
    )

    args = parser.parse_args()

    export_season_images(args.season_id, args.count)


if __name__ == "__main__":
    main()
