"""Add updated_at to cards table

Revision ID: 0044
Revises: 0043
Create Date: 2025-02-17

Adds an `updated_at` column to the `cards` table and backfills it
from `card_images.image_updated_at` so we no longer need to JOIN
on card_images just to get a timestamp.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260217_0044"
down_revision = "20260213_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add the new column
    op.add_column("cards", sa.Column("updated_at", sa.Text(), nullable=True))

    # Backfill from card_images.image_updated_at
    op.execute(
        """
        UPDATE cards
        SET updated_at = (
            SELECT ci.image_updated_at
            FROM card_images ci
            WHERE ci.card_id = cards.id
        )
        """
    )

    # For cards that have no image record, fall back to created_at
    op.execute(
        """
        UPDATE cards
        SET updated_at = created_at
        WHERE updated_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("cards", "updated_at")
