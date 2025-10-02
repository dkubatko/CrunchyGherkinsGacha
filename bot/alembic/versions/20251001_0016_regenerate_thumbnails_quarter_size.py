"""Regenerate all thumbnails at 1/4 scale instead of 1/3

Revision ID: 20251001_0016
Revises: 20240928_0015
Create Date: 2025-10-01 00:00:00.000000

"""

from __future__ import annotations

import base64
import logging
import os
import sys

from alembic import op
from sqlalchemy import text

# Add the bot directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from utils.image import ImageUtil

# revision identifiers, used by Alembic.
revision = "20251001_0016"
down_revision = "20240928_0015"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    """Regenerate all card thumbnails at 1/4 scale for improved performance."""
    connection = op.get_bind()

    select_stmt = text(
        "SELECT id, image_b64 FROM cards WHERE image_b64 IS NOT NULL AND image_b64 != ''"
    )
    update_stmt = text("UPDATE cards SET image_thumb_b64 = :thumb WHERE id = :card_id")

    result = connection.execute(select_stmt)

    # Iterate over results and regenerate thumbnails at 1/4 scale
    processed = 0
    failed = 0
    for row in result.mappings():
        card_id = row["id"]
        image_b64 = row["image_b64"]

        if not image_b64:
            continue

        try:
            image_bytes = base64.b64decode(image_b64)
            # Use 1/4 scale instead of the old 1/3 scale
            thumb_bytes = ImageUtil.compress_to_fraction(image_bytes, scale_factor=1 / 4)
            thumb_b64 = base64.b64encode(thumb_bytes).decode("utf-8")
            connection.execute(update_stmt, {"thumb": thumb_b64, "card_id": card_id})
            processed += 1
        except Exception as exc:  # pragma: no cover - defensive logging during migration
            logger.warning("Failed to regenerate thumbnail for card %s: %s", card_id, exc)
            failed += 1
            continue

    logger.info(
        "Thumbnail regeneration complete: %d processed, %d failed",
        processed,
        failed,
    )


def downgrade() -> None:
    """Regenerate all card thumbnails back to 1/3 scale."""
    connection = op.get_bind()

    select_stmt = text(
        "SELECT id, image_b64 FROM cards WHERE image_b64 IS NOT NULL AND image_b64 != ''"
    )
    update_stmt = text("UPDATE cards SET image_thumb_b64 = :thumb WHERE id = :card_id")

    result = connection.execute(select_stmt)

    # Iterate over results and regenerate thumbnails at 1/3 scale
    for row in result.mappings():
        card_id = row["id"]
        image_b64 = row["image_b64"]

        if not image_b64:
            continue

        try:
            image_bytes = base64.b64decode(image_b64)
            # Use 1/3 scale (the old default)
            thumb_bytes = ImageUtil.compress_to_fraction(image_bytes, scale_factor=1 / 3)
            thumb_b64 = base64.b64encode(thumb_bytes).decode("utf-8")
            connection.execute(update_stmt, {"thumb": thumb_b64, "card_id": card_id})
        except Exception as exc:  # pragma: no cover - defensive logging during migration
            logger.warning(
                "Failed to regenerate thumbnail for card %s during downgrade: %s", card_id, exc
            )
            continue
