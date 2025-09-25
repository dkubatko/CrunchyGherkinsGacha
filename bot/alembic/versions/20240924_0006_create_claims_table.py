"""Create claims table for tracking per-chat claim counts

Revision ID: 20240924_0006
Revises: 20240924_0005
Create Date: 2025-09-24 02:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20240924_0006"
down_revision = "20240924_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "claims",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("user_id", "chat_id"),
    )


def downgrade() -> None:
    op.drop_table("claims")
