"""Rename characters.image column to imageb64 for consistency

Revision ID: 20240928_0014
Revises: 20240928_0013
Create Date: 2025-09-28 15:50:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20240928_0014"
down_revision = "20240928_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename characters.image column to imageb64 for consistency with users table."""
    print("Renaming characters.image to characters.imageb64...")

    connection = op.get_bind()

    # Check if imageb64 column already exists
    result = connection.execute(sa.text("PRAGMA table_info(characters)"))
    columns = [row[1] for row in result.fetchall()]

    if "imageb64" not in columns:
        # Add new column (make it NOT NULL since all characters should have images)
        op.add_column("characters", sa.Column("imageb64", sa.Text(), nullable=False, default=""))
        print("Added imageb64 column")
    else:
        print("imageb64 column already exists, skipping creation")

    # Copy data from old column to new column (if image column still exists)
    if "image" in columns:
        connection.execute(
            sa.text(
                "UPDATE characters SET imageb64 = image WHERE image IS NOT NULL AND (imageb64 IS NULL OR imageb64 = '')"
            )
        )
        print("Copied data from image to imageb64")

        # Drop old column
        op.drop_column("characters", "image")
        print("Dropped old image column")
    else:
        print("image column no longer exists, skipping data copy and drop")

    print("Successfully renamed characters.image to characters.imageb64")


def downgrade() -> None:
    """Rename characters.imageb64 back to image."""
    print("Reverting characters.imageb64 back to characters.image...")

    # Add old column back (make it NOT NULL since all characters should have images)
    op.add_column("characters", sa.Column("image", sa.Text(), nullable=False, default=""))

    # Copy data from new column to old column
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE characters SET image = imageb64 WHERE imageb64 IS NOT NULL"))

    # Drop new column
    op.drop_column("characters", "imageb64")

    print("Successfully reverted characters.imageb64 back to characters.image")
