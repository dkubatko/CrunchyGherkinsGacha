"""Add user_preferences and roll_notifications tables

Revision ID: 20260404_0057
Revises: 20260330_0056
Create Date: 2026-04-04

Adds the user_preferences table for per-user settings (starting with
notify_rolls opt-out) and the roll_notifications table for tracking
scheduled roll availability notifications.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260404_0057"
down_revision = "20260330_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("notify_rolls", sa.Boolean, nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "roll_notifications",
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("chat_id", sa.Text, nullable=False),
        sa.Column("notify_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("user_id", "chat_id"),
    )

    op.create_index(
        "idx_roll_notifications_pending",
        "roll_notifications",
        ["sent", "notify_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_roll_notifications_pending", table_name="roll_notifications")
    op.drop_table("roll_notifications")
    op.drop_table("user_preferences")
