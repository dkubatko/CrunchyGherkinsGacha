"""Add poker_cardb64 column to users and characters tables

Revision ID: 20251112_0032
Revises: 20251112_0031
Create Date: 2025-11-12 00:00:00.000000

"""

from __future__ import annotations

import base64
import os
import sys
from io import BytesIO

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column, select

# Add the bot directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from utils.gemini import GeminiUtil

    GEMINI_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import GeminiUtil: {e}")
    GEMINI_AVAILABLE = False

# revision identifiers, used by Alembic.
revision = "20251112_0032"
down_revision = "20251112_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add poker_cardb64 column to users and characters tables and backfill."""
    # Add the new column to users table
    op.add_column("users", sa.Column("poker_cardb64", sa.Text(), nullable=True))

    # Add the new column to characters table
    op.add_column("characters", sa.Column("poker_cardb64", sa.Text(), nullable=True))

    # Backfill poker cards for existing users and characters
    if GEMINI_AVAILABLE:
        print("Backfilling poker cards for existing users and characters...")

        # Get API credentials from environment
        google_api_key = os.getenv("GOOGLE_API_KEY")
        image_gen_model = os.getenv("IMAGE_GEN_MODEL")

        if not google_api_key or not image_gen_model:
            print(
                "Warning: GOOGLE_API_KEY or IMAGE_GEN_MODEL not set. Skipping poker card backfill."
            )
            return

        # Initialize Gemini utility
        gemini_util = GeminiUtil(google_api_key, image_gen_model)

        # Get database connection
        conn = op.get_bind()

        # Define table structures
        users_table = table(
            "users",
            column("user_id", sa.Integer),
            column("username", sa.Text),
            column("profile_imageb64", sa.Text),
            column("poker_cardb64", sa.Text),
        )

        characters_table = table(
            "characters",
            column("id", sa.Integer),
            column("name", sa.Text),
            column("imageb64", sa.Text),
            column("poker_cardb64", sa.Text),
        )

        # Backfill users
        users = conn.execute(
            select(
                users_table.c.user_id, users_table.c.username, users_table.c.profile_imageb64
            ).where(
                sa.and_(
                    users_table.c.profile_imageb64.isnot(None), users_table.c.profile_imageb64 != ""
                )
            )
        ).fetchall()

        print(f"Found {len(users)} users with profile images to backfill")
        users_success = 0
        users_failed = 0

        for user in users:
            user_id, username, profile_imageb64 = user

            # Validate base64
            try:
                base64.b64decode(profile_imageb64)
            except Exception:
                print(f"  ⏭️  Skipping user {username} - invalid base64")
                continue

            print(f"  Generating poker card for user: {username}")
            try:
                poker_cardb64 = gemini_util.generate_poker_card(base_image_b64=profile_imageb64)

                if poker_cardb64:
                    conn.execute(
                        users_table.update()
                        .where(users_table.c.user_id == user_id)
                        .values(poker_cardb64=poker_cardb64)
                    )
                    print(f"    ✅ Success")
                    users_success += 1
                else:
                    print(f"    ❌ Failed")
                    users_failed += 1
            except Exception as e:
                print(f"    ❌ Error: {e}")
                users_failed += 1

        # Backfill characters
        characters = conn.execute(
            select(
                characters_table.c.id, characters_table.c.name, characters_table.c.imageb64
            ).where(
                sa.and_(characters_table.c.imageb64.isnot(None), characters_table.c.imageb64 != "")
            )
        ).fetchall()

        print(f"\nFound {len(characters)} characters with images to backfill")
        characters_success = 0
        characters_failed = 0

        for character in characters:
            character_id, name, imageb64 = character

            # Validate base64
            try:
                base64.b64decode(imageb64)
            except Exception:
                print(f"  ⏭️  Skipping character {name} - invalid base64")
                continue

            print(f"  Generating poker card for character: {name}")
            try:
                poker_cardb64 = gemini_util.generate_poker_card(base_image_b64=imageb64)

                if poker_cardb64:
                    conn.execute(
                        characters_table.update()
                        .where(characters_table.c.id == character_id)
                        .values(poker_cardb64=poker_cardb64)
                    )
                    print(f"    ✅ Success")
                    characters_success += 1
                else:
                    print(f"    ❌ Failed")
                    characters_failed += 1
            except Exception as e:
                print(f"    ❌ Error: {e}")
                characters_failed += 1

        print("\n" + "=" * 60)
        print("BACKFILL SUMMARY")
        print("=" * 60)
        print(f"Users:      ✅ {users_success} success, ❌ {users_failed} failed")
        print(f"Characters: ✅ {characters_success} success, ❌ {characters_failed} failed")
        print("=" * 60)
    else:
        print("Warning: GeminiUtil not available. Skipping poker card backfill.")


def downgrade() -> None:
    """Remove poker_cardb64 column from users and characters tables."""
    # Remove the column from characters table
    op.drop_column("characters", "poker_cardb64")

    # Remove the column from users table
    op.drop_column("users", "poker_cardb64")
