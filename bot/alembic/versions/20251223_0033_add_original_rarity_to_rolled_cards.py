"""Add original_rarity column to rolled_cards table

Revision ID: 20251223_0033
Revises: 20251112_0032
Create Date: 2024-12-23 12:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251223_0033"
down_revision = "20251112_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rolled_cards",
        sa.Column("original_rarity", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rolled_cards", "original_rarity")
