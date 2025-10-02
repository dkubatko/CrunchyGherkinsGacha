"""Create threads table

Revision ID: 20251001_0017
Revises: 20251001_0016
Create Date: 2025-10-01 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251001_0017"
down_revision = "20251001_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "threads",
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("chat_id"),
    )


def downgrade() -> None:
    op.drop_table("threads")
