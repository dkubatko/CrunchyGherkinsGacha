"""Add slot_iconb64 column to users table and backfill with generated icons

Revision ID: 20240928_0012
Revises: 20241002_0011
Create Date: 2025-09-28 15:25:00.000000

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
revision = "20240928_0012"
down_revision = "20241002_0011"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    """Add slot_iconb64 column and backfill with generated slot machine icons."""
    # Add the new column
    op.add_column("users", sa.Column("slot_iconb64", sa.Text(), nullable=True))

    # Backfill existing users with slot machine icons
    if GEMINI_AVAILABLE:
        print("Backfilling slot machine icons for existing users...")
        backfill_slot_icons()
    else:
        print("Gemini utilities not available. Skipping slot icon generation.")


def backfill_slot_icons():
    """Generate slot machine icons for all users with profile images."""
    connection = op.get_bind()

    # Get all users with profile images
    users_table = table(
        "users",
        column("user_id", sa.Integer()),
        column("username", sa.Text()),
        column("display_name", sa.Text()),
        column("profile_imageb64", sa.Text()),
        column("slot_iconb64", sa.Text()),
    )

    # Query users with profile images
    result = connection.execute(
        select(users_table.c.user_id, users_table.c.username, users_table.c.profile_imageb64)
        .where(users_table.c.profile_imageb64.isnot(None))
        .where(users_table.c.profile_imageb64 != "")
    )

    users_with_profiles = result.fetchall()
    total_users = len(users_with_profiles)

    if total_users == 0:
        print("No users with profile images found.")
        return

    print(f"Found {total_users} users with profile images. Generating slot machine icons...")

    # Initialize Gemini utility
    try:
        gemini_util = GeminiUtil()
    except Exception as e:
        print(f"Failed to initialize Gemini utility: {e}")
        return

    success_count = 0

    for i, user in enumerate(users_with_profiles, 1):
        user_id, username, profile_imageb64 = user

        try:
            print(f"[{i}/{total_users}] Generating slot icon for @{username} (ID: {user_id})...")

            # Generate slot machine icon
            slot_icon_b64 = gemini_util.generate_slot_machine_icon(base_image_b64=profile_imageb64)

            if slot_icon_b64:
                # Update user with generated slot icon
                connection.execute(
                    users_table.update()
                    .where(users_table.c.user_id == user_id)
                    .values(slot_iconb64=slot_icon_b64)
                )
                success_count += 1
                print(f"✅ Generated slot icon for @{username}")
            else:
                print(f"❌ Failed to generate slot icon for @{username}")

        except Exception as e:
            print(f"❌ Error generating slot icon for @{username}: {e}")
            continue

    print(f"Backfill complete: {success_count}/{total_users} slot icons generated successfully.")


def downgrade() -> None:
    """Remove slot_iconb64 column from users table."""
    op.drop_column("users", "slot_iconb64")
