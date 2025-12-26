"""Create ride the bus games table

Revision ID: 20251224_0035
Revises: 20251223_0034
Create Date: 2024-12-24 10:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251224_0035"
down_revision = "20251223_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create rtb_games table for Ride the Bus game tracking."""
    op.create_table(
        "rtb_games",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.String(), nullable=False),
        # Bet in spins (10-50)
        sa.Column("bet_amount", sa.Integer(), nullable=False),
        # JSON array of 5 card IDs selected for the game
        sa.Column("card_ids", sa.String(), nullable=False),
        # JSON array of 5 card rarities (preserved even if cards are deleted)
        sa.Column("card_rarities", sa.String(), nullable=False),
        # JSON array of 5 card titles (preserved even if cards are deleted)
        sa.Column("card_titles", sa.String(), nullable=False),
        # Current position in the game (0-4, how many cards have been revealed)
        sa.Column("current_position", sa.Integer(), nullable=False, server_default="1"),
        # Current multiplier (starts at x2, progresses: x2 -> x3 -> x5 -> x10)
        sa.Column("current_multiplier", sa.Integer(), nullable=False, server_default="2"),
        # Game status: 'active', 'won', 'lost', 'cashed_out'
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        # Timestamps
        sa.Column("started_timestamp", sa.DateTime(), nullable=False),
        sa.Column("last_updated_timestamp", sa.DateTime(), nullable=False),
    )

    # Create index on user_id and chat_id for fast lookups of active games
    op.create_index("idx_rtb_user_chat", "rtb_games", ["user_id", "chat_id"])

    # Create index on status for filtering active games
    op.create_index("idx_rtb_status", "rtb_games", ["status"])

    # Create index on started_timestamp for cleanup/analytics
    op.create_index("idx_rtb_started", "rtb_games", ["started_timestamp"])


def downgrade() -> None:
    """Drop rtb_games table."""
    op.drop_index("idx_rtb_started", table_name="rtb_games")
    op.drop_index("idx_rtb_status", table_name="rtb_games")
    op.drop_index("idx_rtb_user_chat", table_name="rtb_games")
    op.drop_table("rtb_games")
