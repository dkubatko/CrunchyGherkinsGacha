"""Replace time-based spin refresh with daily login bonus

Revision ID: 20260213_0043
Revises: 20260120_0042
Create Date: 2026-02-13 00:00:00.000000

This migration replaces the old time-based spin refresh system with a daily
login bonus streak system. It:
- Adds login_streak (INTEGER NOT NULL DEFAULT 0) to spins table
- Adds last_bonus_date (TEXT, nullable) to spins table
- Drops refresh_timestamp from spins table
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260213_0043"
down_revision = "20260120_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add daily bonus columns and drop refresh_timestamp."""
    op.add_column(
        "spins",
        sa.Column("login_streak", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "spins",
        sa.Column("last_bonus_date", sa.Text(), nullable=True),
    )
    # SQLite doesn't support DROP COLUMN before 3.35.0, so we recreate the table
    # Using batch mode for SQLite compatibility
    with op.batch_alter_table("spins") as batch_op:
        batch_op.drop_column("refresh_timestamp")


def downgrade() -> None:
    """Restore refresh_timestamp and drop daily bonus columns."""
    with op.batch_alter_table("spins") as batch_op:
        batch_op.add_column(
            sa.Column("refresh_timestamp", sa.Text(), nullable=False, server_default=""),
        )
        batch_op.drop_column("last_bonus_date")
        batch_op.drop_column("login_streak")
