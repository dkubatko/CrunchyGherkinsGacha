"""Create spins table and backfill from chats

Revision ID: 20240928_0015
Revises: 20240928_0014
Create Date: 2024-09-28 15:30:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import column, table, text

# revision identifiers, used by Alembic.
revision = "20240928_0015"
down_revision = "20240928_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create spins table and backfill with data from chats table."""
    # Create the spins table
    op.create_table(
        "spins",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("refresh_timestamp", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "chat_id"),
    )

    # Backfill spins table with data from chats table
    connection = op.get_bind()

    # Get current timestamp in ISO format
    from datetime import datetime

    current_timestamp = datetime.now().isoformat()

    # Insert data from chats table with default count=10 and current timestamp
    connection.execute(
        text(
            """
            INSERT INTO spins (user_id, chat_id, count, refresh_timestamp)
            SELECT user_id, chat_id, 10, :timestamp
            FROM chats
        """
        ),
        {"timestamp": current_timestamp},
    )


def downgrade() -> None:
    """Drop the spins table."""
    op.drop_table("spins")
