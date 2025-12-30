"""Create achievements tables

Revision ID: 20251229_0040
Revises: 20251228_0039
Create Date: 2025-12-29 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251229_0040"
down_revision = "20251228_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create achievements and user_achievements tables."""
    # Create achievements table for achievement definitions
    op.create_table(
        "achievements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon_b64", sa.Text(), nullable=True),
    )

    # Create user_achievements table for tracking which users have which achievements
    op.create_table(
        "user_achievements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "achievement_id",
            sa.Integer(),
            sa.ForeignKey("achievements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("unlocked_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),
    )

    # Create indexes for common query patterns
    op.create_index("idx_user_achievements_user_id", "user_achievements", ["user_id"])
    op.create_index("idx_user_achievements_achievement_id", "user_achievements", ["achievement_id"])


def downgrade() -> None:
    """Drop achievements tables."""
    op.drop_index("idx_user_achievements_achievement_id", table_name="user_achievements")
    op.drop_index("idx_user_achievements_user_id", table_name="user_achievements")
    op.drop_table("user_achievements")
    op.drop_table("achievements")
