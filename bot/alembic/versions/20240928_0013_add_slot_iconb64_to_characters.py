"""Add slot_iconb64 column to characters table and backfill with generated icons

Revision ID: 20240928_0013
Revises: 20240928_0012
Create Date: 2025-09-28 15:32:00.000000

"""

from __future__ import annotations

import base64
import logging
import os
import sys
from io import BytesIO

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import column, table, select
from sqlalchemy import text

# Add the bot directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from utils.gemini import GeminiUtil
    from utils.image import ImageUtil

    GEMINI_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import Gemini utilities: {e}")
    GEMINI_AVAILABLE = False

# revision identifiers, used by Alembic.
revision = "20240928_0013"
down_revision = "20240928_0012"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    """Add slot_iconb64 column and backfill with generated slot machine icons."""
    # Add the new column
    op.add_column("characters", sa.Column("slot_iconb64", sa.Text(), nullable=True))

    # Backfill existing characters with slot machine icons
    if GEMINI_AVAILABLE:
        print("Backfilling slot machine icons for existing characters...")
        backfill_character_slot_icons()
    else:
        print("Gemini utilities not available. Skipping slot icon generation for characters.")


def backfill_character_slot_icons():
    """Generate slot machine icons for all characters with images."""
    connection = op.get_bind()

    # Get all characters with images
    characters_table = table(
        "characters",
        column("id", sa.Integer()),
        column("chat_id", sa.Text()),
        column("name", sa.Text()),
        column("image", sa.Text()),
        column("slot_iconb64", sa.Text()),
    )

    # Query all characters with images
    result = connection.execute(
        select(
            characters_table.c.id,
            characters_table.c.name,
            characters_table.c.chat_id,
            characters_table.c.image,
        )
        .where(characters_table.c.image.isnot(None))
        .where(characters_table.c.image != "")
    )

    characters_with_images = result.fetchall()
    total_characters = len(characters_with_images)

    if total_characters == 0:
        print("No characters with images found.")
        return

    print(f"Found {total_characters} characters with images. Generating slot machine icons...")

    # Initialize Gemini utility
    try:
        gemini_util = GeminiUtil()
    except Exception as e:
        print(f"Failed to initialize Gemini utility: {e}")
        return

    success_count = 0

    for i, character in enumerate(characters_with_images, 1):
        character_id, name, chat_id, image_b64 = character

        try:
            print(
                f"[{i}/{total_characters}] Generating slot icon for character '{name}' (ID: {character_id}, Chat: {chat_id})..."
            )

            # Generate slot machine icon
            slot_icon_b64 = gemini_util.generate_slot_machine_icon(base_image_b64=image_b64)

            if slot_icon_b64:
                # Update character with generated slot icon
                connection.execute(
                    characters_table.update()
                    .where(characters_table.c.id == character_id)
                    .values(slot_iconb64=slot_icon_b64)
                )
                success_count += 1
                print(f"✅ Generated slot icon for character '{name}'")
            else:
                print(f"❌ Failed to generate slot icon for character '{name}'")

        except Exception as e:
            print(f"❌ Error generating slot icon for character '{name}': {e}")
            continue

    print(
        f"Character backfill complete: {success_count}/{total_characters} slot icons generated successfully."
    )


def downgrade() -> None:
    """Remove slot_iconb64 column from characters table."""
    op.drop_column("characters", "slot_iconb64")
