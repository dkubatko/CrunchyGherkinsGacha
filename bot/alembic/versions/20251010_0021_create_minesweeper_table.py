"""create minesweeper table

Revision ID: 20251010_0021
Revises: 20251008_0020
Create Date: 2025-01-10

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20251010_0021"
down_revision: Union[str, None] = "20251008_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create minesweeper games table."""
    op.create_table(
        "minesweeper_games",
        sa.Column("id", sa.Integer(), nullable=False, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("bet_card_id", sa.Integer(), nullable=False),
        sa.Column(
            "mine_positions", sa.String(), nullable=False
        ),  # JSON string of mine positions e.g. "[0,4,8]"
        sa.Column(
            "claim_point_positions", sa.String(), nullable=False
        ),  # JSON string of claim point positions e.g. "[5]"
        sa.Column(
            "revealed_cells", sa.String(), nullable=False, server_default="[]"
        ),  # JSON string of revealed cell indices e.g. "[1,2,3]"
        sa.Column(
            "status", sa.String(), nullable=False, server_default="active"
        ),  # 'active', 'won', 'lost'
        sa.Column("moves_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reward_card_id", sa.Integer(), nullable=True),  # Card won (if status='won')
        sa.Column("started_timestamp", sa.DateTime(), nullable=False),
        sa.Column("last_updated_timestamp", sa.DateTime(), nullable=False),
    )

    # Create index on user_id and chat_id for fast lookups
    op.create_index("idx_minesweeper_user_chat", "minesweeper_games", ["user_id", "chat_id"])

    # Create index on status for filtering active games
    op.create_index("idx_minesweeper_status", "minesweeper_games", ["status"])

    # Create index on started_timestamp for cleanup/analytics
    op.create_index("idx_minesweeper_started", "minesweeper_games", ["started_timestamp"])


def downgrade() -> None:
    """Drop minesweeper games table."""
    op.drop_index("idx_minesweeper_started", table_name="minesweeper_games")
    op.drop_index("idx_minesweeper_status", table_name="minesweeper_games")
    op.drop_index("idx_minesweeper_user_chat", table_name="minesweeper_games")
    op.drop_table("minesweeper_games")
