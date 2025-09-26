"""Create rolled_cards table for tracking roll state

Revision ID: 20241001_0008
Revises: 20240926_0007
Create Date: 2024-10-01 00:00:00.000000

"""

from __future__ import annotations

import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "20241001_0008"
down_revision = "20240926_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create rolled_cards table
    op.create_table(
        "rolled_cards",
        sa.Column("card_id", sa.Integer(), sa.ForeignKey("cards.id"), primary_key=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("original_roller_id", sa.Integer(), nullable=False),
        sa.Column("rerolled", sa.Boolean(), nullable=False, default=False),
        sa.Column("being_rerolled", sa.Boolean(), nullable=False, default=False),
        sa.Column("attempted_by", sa.Text(), nullable=True),
        sa.Column("is_locked", sa.Boolean(), nullable=False, default=False),
        sa.Column("original_rarity", sa.Text(), nullable=True),
    )

    # Create index for performance
    op.create_index("ix_rolled_cards_original_roller_id", "rolled_cards", ["original_roller_id"])

    connection = op.get_bind()

    # Backfill rolled_cards table from existing cards that are unclaimed (recently rolled)
    # We'll identify these as cards created within the last 24 hours that have no owner
    now = datetime.datetime.now()
    cutoff_time = (now - datetime.timedelta(hours=24)).isoformat()

    # For unclaimed cards created recently, we can't determine the original roller
    # So we'll create a default entry for those cards with original_roller_id = 0 (unknown)
    backfill_unclaimed_stmt = text(
        """
        INSERT INTO rolled_cards (card_id, created_at, original_roller_id, rerolled, being_rerolled, attempted_by, is_locked, original_rarity)
        SELECT 
            id as card_id,
            COALESCE(created_at, :now) as created_at,
            0 as original_roller_id,
            0 as rerolled,
            0 as being_rerolled,
            attempted_by,
            0 as is_locked,
            NULL as original_rarity
        FROM cards 
        WHERE owner IS NULL 
        AND created_at > :cutoff_time
    """
    )

    connection.execute(
        backfill_unclaimed_stmt, {"now": now.isoformat(), "cutoff_time": cutoff_time}
    )

    # Drop redundant columns from cards table now that we're tracking this in rolled_cards
    op.drop_column("cards", "attempted_by")


def downgrade() -> None:
    # Restore attempted_by column to cards table
    op.add_column("cards", sa.Column("attempted_by", sa.Text(), nullable=True))

    # Migrate data back from rolled_cards to cards before dropping the table
    connection = op.get_bind()
    restore_stmt = text(
        """
        UPDATE cards 
        SET attempted_by = (
            SELECT attempted_by 
            FROM rolled_cards 
            WHERE rolled_cards.card_id = cards.id
        )
        WHERE id IN (SELECT card_id FROM rolled_cards)
    """
    )
    connection.execute(restore_stmt)

    op.drop_index("ix_rolled_cards_original_roller_id")
    op.drop_table("rolled_cards")
