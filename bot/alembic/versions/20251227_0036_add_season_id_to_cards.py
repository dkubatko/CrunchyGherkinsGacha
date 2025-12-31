"""Add season_id to cards table for season tracking

Revision ID: 20251227_0036
Revises: 20251224_0035
Create Date: 2025-12-27 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251227_0036"
down_revision = "20251224_0035"
branch_labels = None
depends_on = None

# Default season for existing cards
DEFAULT_SEASON_ID = 0


def upgrade() -> None:
    """Add season_id column to cards table and create index."""
    # Add nullable column first
    op.add_column("cards", sa.Column("season_id", sa.Integer(), nullable=True))

    # Set default value for existing cards
    conn = op.get_bind()
    cards_table = sa.table(
        "cards",
        sa.column("season_id", sa.Integer),
    )
    conn.execute(
        sa.update(cards_table)
        .where(cards_table.c.season_id.is_(None))
        .values(season_id=DEFAULT_SEASON_ID)
    )

    # Make column non-nullable now that all rows have a value
    with op.batch_alter_table("cards") as batch_op:
        batch_op.alter_column("season_id", nullable=False)

    # Create index for efficient season filtering
    op.create_index("idx_cards_season_id", "cards", ["season_id"])

    # Create composite index for common query pattern
    op.create_index("idx_cards_season_user", "cards", ["season_id", "user_id"])


def downgrade() -> None:
    """Remove season_id column and indices from cards table."""
    op.drop_index("idx_cards_season_user", table_name="cards")
    op.drop_index("idx_cards_season_id", table_name="cards")
    op.drop_column("cards", "season_id")
