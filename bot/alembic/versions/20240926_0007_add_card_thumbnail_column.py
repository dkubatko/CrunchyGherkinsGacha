"""Add image_thumb_b64 column with backfilled thumbnails

Revision ID: 20240926_0007
Revises: 20240924_0006
Create Date: 2025-09-26 00:00:00.000000

"""

from __future__ import annotations

import base64
import logging

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

from utils.image import ImageUtil

# revision identifiers, used by Alembic.
revision = "20240926_0007"
down_revision = "20240924_0006"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    op.add_column("cards", sa.Column("image_thumb_b64", sa.Text(), nullable=True))

    connection = op.get_bind()

    select_stmt = text(
        "SELECT id, image_b64 FROM cards WHERE image_b64 IS NOT NULL AND image_b64 != ''"
    )
    update_stmt = text("UPDATE cards SET image_thumb_b64 = :thumb WHERE id = :card_id")

    result = connection.execute(select_stmt)

    # Iterate over results and populate thumbnails
    for row in result.mappings():
        card_id = row["id"]
        image_b64 = row["image_b64"]

        if not image_b64:
            continue

        try:
            image_bytes = base64.b64decode(image_b64)
            thumb_bytes = ImageUtil.compress_to_fraction(image_bytes)
            thumb_b64 = base64.b64encode(thumb_bytes).decode("utf-8")
        except Exception as exc:  # pragma: no cover - defensive logging during migration
            logger.warning("Failed to backfill thumbnail for card %s: %s", card_id, exc)
            continue

        connection.execute(update_stmt, {"thumb": thumb_b64, "card_id": card_id})


def downgrade() -> None:
    op.drop_column("cards", "image_thumb_b64")
