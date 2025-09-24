"""Initial schema

Revision ID: 20240924_0001
Revises: None
Create Date: 2025-09-24 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20240924_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cards",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("base_name", sa.Text(), nullable=False),
        sa.Column("modifier", sa.Text(), nullable=False),
        sa.Column("rarity", sa.Text(), nullable=False),
        sa.Column("owner", sa.Text(), nullable=True),
        sa.Column("image_b64", sa.Text(), nullable=True),
        sa.Column("attempted_by", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("file_id", sa.Text(), nullable=True),
        sa.Column("chat_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=True),
    )

    op.create_table(
        "user_rolls",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("last_roll_timestamp", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_rolls")
    op.drop_table("cards")
