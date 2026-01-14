"""Create modifier_counts table for tracking modifier frequency

Revision ID: 20260114_0041
Revises: 20251229_0040
Create Date: 2026-01-14 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260114_0041"
down_revision = "20251229_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create modifier_counts table for incremental modifier frequency tracking."""
    op.create_table(
        "modifier_counts",
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("modifier", sa.Text(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, default=0),
        sa.PrimaryKeyConstraint("chat_id", "season_id", "modifier"),
    )

    # Create index for efficient lookups by chat_id and season_id
    op.create_index(
        "idx_modifier_counts_chat_season",
        "modifier_counts",
        ["chat_id", "season_id"],
    )


def downgrade() -> None:
    """Drop modifier_counts table."""
    op.drop_index("idx_modifier_counts_chat_season", table_name="modifier_counts")
    op.drop_table("modifier_counts")
