"""Add performance indices to cards table

Revision ID: 20251026_0030
Revises: 20251018_0029
Create Date: 2025-10-26 18:30:00.000000

This migration adds critical indices to the cards table to dramatically improve
query performance for the most common access patterns:
- user_id lookups (used by get_user_collection)
- owner lookups (used by get_user_collection fallback)
- chat_id lookups (used for filtering collections by chat)
- Combined user_id + chat_id (used for scoped user collections)
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251026_0029"
down_revision = "20251016_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add indices to cards table for common query patterns."""

    # Index for user_id lookups - most common query pattern
    op.create_index("idx_cards_user_id", "cards", ["user_id"])

    # Index for owner lookups - used as fallback in get_user_collection
    op.create_index("idx_cards_owner", "cards", ["owner"])

    # Index for chat_id filtering
    op.create_index("idx_cards_chat_id", "cards", ["chat_id"])

    # Composite index for user_id + chat_id - optimizes scoped queries
    op.create_index("idx_cards_user_chat", "cards", ["user_id", "chat_id"])

    # Composite index for owner + chat_id - optimizes scoped owner queries
    op.create_index("idx_cards_owner_chat", "cards", ["owner", "chat_id"])

    # Index for chats table to optimize JOIN on user_id
    # The composite PK (chat_id, user_id) helps with chat_id lookups,
    # but not with user_id lookups needed for the JOIN
    op.create_index("idx_chats_user_id", "chats", ["user_id"])


def downgrade() -> None:
    """Remove indices from cards and chats tables."""
    op.drop_index("idx_chats_user_id", "chats")
    op.drop_index("idx_cards_owner_chat", "cards")
    op.drop_index("idx_cards_user_chat", "cards")
    op.drop_index("idx_cards_chat_id", "cards")
    op.drop_index("idx_cards_owner", "cards")
    op.drop_index("idx_cards_user_id", "cards")
