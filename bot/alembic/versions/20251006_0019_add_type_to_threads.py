"""Add type column to threads table

Revision ID: 20251006_0019
Revises: 20251001_0018
Create Date: 2025-10-06 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251006_0019"
down_revision = "20251001_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite doesn't support altering primary keys directly, so we need to recreate the table
    # Create a new table with the correct schema
    op.create_table(
        "threads_new",
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False, server_default="main"),
        sa.PrimaryKeyConstraint("chat_id", "type"),
    )

    # Copy existing data with default type='main'
    op.execute(
        """
        INSERT INTO threads_new (chat_id, thread_id, type)
        SELECT chat_id, thread_id, 'main'
        FROM threads
        """
    )

    # Drop the old table
    op.drop_table("threads")

    # Rename the new table to the original name
    op.rename_table("threads_new", "threads")


def downgrade() -> None:
    # Recreate the original table structure
    op.create_table(
        "threads_old",
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("chat_id"),
    )

    # Copy data back, keeping only 'main' type entries
    op.execute(
        """
        INSERT INTO threads_old (chat_id, thread_id)
        SELECT chat_id, thread_id
        FROM threads
        WHERE type = 'main'
        """
    )

    # Drop the new table
    op.drop_table("threads")

    # Rename back
    op.rename_table("threads_old", "threads")
