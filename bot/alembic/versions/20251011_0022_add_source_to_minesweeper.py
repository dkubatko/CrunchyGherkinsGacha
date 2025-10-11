"""add source tracking to minesweeper games

Revision ID: 20251011_0022
Revises: 20251010_0021
Create Date: 2025-01-11

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20251011_0022"
down_revision: Union[str, None] = "20251010_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add source_type and source_id columns to minesweeper_games table."""
    # Add source_type column (user or character)
    op.add_column(
        "minesweeper_games",
        sa.Column("source_type", sa.String(), nullable=True),
    )

    # Add source_id column (user_id for users, character id for characters)
    op.add_column(
        "minesweeper_games",
        sa.Column("source_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Remove source_type and source_id columns from minesweeper_games table."""
    op.drop_column("minesweeper_games", "source_id")
    op.drop_column("minesweeper_games", "source_type")
