"""Add chat_id to user_rolls for per-chat tracking

Revision ID: 20240924_0005
Revises: 20240924_0004
Create Date: 2025-09-24 01:45:00.000000

"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa
from dotenv import load_dotenv

# revision identifiers, used by Alembic.
revision = "20240924_0005"
down_revision = "20240924_0004"
branch_labels = None
depends_on = None

load_dotenv()


def upgrade() -> None:
    bind = op.get_bind()

    existing_rows = bind.execute(sa.text("SELECT COUNT(*) FROM user_rolls")).scalar() or 0

    group_chat_id = os.getenv("GROUP_CHAT_ID")
    if existing_rows and not group_chat_id:
        raise RuntimeError(
            "GROUP_CHAT_ID environment variable must be set to backfill user_rolls.chat_id"
        )

    op.create_table(
        "user_rolls_new",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("last_roll_timestamp", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "chat_id"),
    )

    if existing_rows:
        bind.execute(
            sa.text(
                """
                INSERT INTO user_rolls_new (user_id, chat_id, last_roll_timestamp)
                SELECT user_id, :chat_id, last_roll_timestamp FROM user_rolls
                """
            ),
            {"chat_id": str(group_chat_id)},
        )

    op.drop_table("user_rolls")
    op.rename_table("user_rolls_new", "user_rolls")


def downgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "user_rolls_legacy",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("last_roll_timestamp", sa.Text(), nullable=False),
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO user_rolls_legacy (user_id, last_roll_timestamp)
            SELECT user_id, MAX(last_roll_timestamp)
            FROM user_rolls
            GROUP BY user_id
            """
        )
    )

    op.drop_table("user_rolls")
    op.rename_table("user_rolls_legacy", "user_rolls")
