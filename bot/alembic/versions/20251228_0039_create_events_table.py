"""Create events table for telemetry

Revision ID: 20251228_0039
Revises: 20251227_0038
Create Date: 2025-12-28 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251228_0039"
down_revision = "20251227_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create events table for telemetry logging."""
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),  # JSON blob
    )

    # Create indexes for common query patterns
    op.create_index("idx_events_type_outcome", "events", ["event_type", "outcome"])
    op.create_index("idx_events_user_timestamp", "events", ["user_id", "timestamp"])
    op.create_index("idx_events_chat_timestamp", "events", ["chat_id", "timestamp"])
    op.create_index("idx_events_card_id", "events", ["card_id"])


def downgrade() -> None:
    """Drop events table."""
    op.drop_index("idx_events_card_id", table_name="events")
    op.drop_index("idx_events_chat_timestamp", table_name="events")
    op.drop_index("idx_events_user_timestamp", table_name="events")
    op.drop_index("idx_events_type_outcome", table_name="events")
    op.drop_table("events")
