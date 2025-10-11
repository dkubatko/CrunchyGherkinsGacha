"""add bet_card_title and bet_card_rarity to minesweeper games

Revision ID: 20251011_0023
Revises: 20251011_0022
Create Date: 2025-10-11

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20251011_0023"
down_revision: Union[str, None] = "20251011_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add bet_card_title and bet_card_rarity columns to minesweeper_games table."""
    # Add bet_card_title column to store the card title even after card is deleted
    op.add_column(
        "minesweeper_games",
        sa.Column("bet_card_title", sa.String(), nullable=True),
    )

    # Add bet_card_rarity column to store the card rarity even after card is deleted
    op.add_column(
        "minesweeper_games",
        sa.Column("bet_card_rarity", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Remove bet_card_title and bet_card_rarity columns from minesweeper_games table."""
    op.drop_column("minesweeper_games", "bet_card_rarity")
    op.drop_column("minesweeper_games", "bet_card_title")
