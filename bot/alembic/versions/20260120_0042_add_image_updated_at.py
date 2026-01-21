"""Add image_updated_at column to card_images table

Revision ID: 20260120_0042
Revises: 20260114_0041
Create Date: 2026-01-20 00:00:00.000000

This migration adds a timestamp column to track when card images were last updated.
This allows the frontend to cache images efficiently by checking if the local
cache is stale compared to the server timestamp.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260120_0042"
down_revision = "20260114_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add image_updated_at column to card_images table."""
    op.add_column(
        "card_images",
        sa.Column("image_updated_at", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove image_updated_at column from card_images table."""
    op.drop_column("card_images", "image_updated_at")
