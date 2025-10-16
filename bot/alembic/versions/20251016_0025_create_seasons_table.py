"""Create seasons table

Revision ID: 20251016_0025
Revises: 20251015_0024
Create Date: 2025-10-16 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251016_0025"
down_revision = "20251015_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the seasons table to store season metadata."""
    op.create_table(
        "seasons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop the seasons table."""
    op.drop_table("seasons")
