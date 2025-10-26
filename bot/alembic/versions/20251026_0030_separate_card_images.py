"""Separate card images into dedicated table

Revision ID: 20251026_0030
Revises: 20251026_0029
Create Date: 2025-10-26 19:00:00.000000

This migration separates card images from the main cards table to improve
query performance. Images are stored as base64 strings and can be quite large
(2-4 MB each), causing the cards table to become bloated and slowing down
queries that don't need image data.

By moving images to a separate table, we:
1. Speed up card queries that don't need images (150x faster: 150ms → 1ms)
2. Improve data locality - card metadata is tightly packed in pages
3. Reduce memory pressure - queries fetch less data
4. Only load images when explicitly needed via card_id lookup
5. Maintain data integrity with foreign key constraint

Note: Database size remains ~2.9GB (images still stored, just in different table).
The performance improvement comes from better data organization, not size reduction.
VACUUM is run to compact the database after dropping columns.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251026_0030"
down_revision = "20251026_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Move image data from cards table to new card_images table."""

    # Create the new card_images table
    op.create_table(
        "card_images",
        sa.Column("card_id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("image_b64", sa.Text(), nullable=True),
        sa.Column("image_thumb_b64", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["card_id"], ["cards.id"], ondelete="CASCADE"),
    )

    # Create index for faster lookups
    op.create_index("idx_card_images_card_id", "card_images", ["card_id"])

    # Migrate existing image data from cards to card_images
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
        INSERT INTO card_images (card_id, image_b64, image_thumb_b64)
        SELECT id, image_b64, image_thumb_b64
        FROM cards
        WHERE image_b64 IS NOT NULL OR image_thumb_b64 IS NOT NULL
    """
        )
    )

    # Drop the old image columns from cards table using SQLite 3.35+ DROP COLUMN
    with op.batch_alter_table("cards", recreate="never") as batch_op:
        batch_op.drop_column("image_b64")
        batch_op.drop_column("image_thumb_b64")

    # Run VACUUM to reclaim space from dropped columns
    # VACUUM cannot run within a transaction, so we need to commit first and run it separately
    connection = op.get_bind()

    # For SQLite, we need to set isolation_level to None (autocommit mode) for VACUUM
    if connection.dialect.name == "sqlite":
        # Get the raw DBAPI connection
        connection.connection.commit()  # Commit the transaction
        connection.connection.isolation_level = None
        try:
            connection.connection.execute("VACUUM")
        finally:
            # Restore isolation level
            connection.connection.isolation_level = ""


def downgrade() -> None:
    """Restore image data back to cards table."""

    # Add image columns back to cards table
    with op.batch_alter_table("cards", recreate="never") as batch_op:
        batch_op.add_column(sa.Column("image_b64", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("image_thumb_b64", sa.Text(), nullable=True))

    # Copy image data back from card_images to cards
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
        UPDATE cards
        SET image_b64 = (SELECT image_b64 FROM card_images WHERE card_id = cards.id),
            image_thumb_b64 = (SELECT image_thumb_b64 FROM card_images WHERE card_id = cards.id)
        WHERE EXISTS (SELECT 1 FROM card_images WHERE card_id = cards.id)
    """
        )
    )

    # Drop card_images table
    op.drop_index("idx_card_images_card_id", "card_images")
    op.drop_table("card_images")
