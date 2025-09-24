"""Create chats table and backfill

Revision ID: 20240924_0003
Revises: 20240924_0002
Create Date: 2025-09-24 01:00:00.000000

"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa
from dotenv import load_dotenv
from sqlalchemy.sql import column, table

# revision identifiers, used by Alembic.
revision = "20240924_0003"
down_revision = "20240924_0002"
branch_labels = None
depends_on = None

USERNAME_TO_ID = {
    "krypthos": 1101242859,
    "brvsnshn": 305677569,
    "sonyabkim": 488359360,
    "matulka": 138354478,
    "maxelnot": 444838873,
    "imkht": 424292432,
    "max_zubatov": 487831762,
    "gabe_mkh": 1093842515,
    "yokocookie": 1395886306,
}

load_dotenv()


def upgrade() -> None:
    op.create_table(
        "chats",
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("chat_id", "user_id"),
    )

    group_chat_id = os.getenv("GROUP_CHAT_ID")
    if not group_chat_id:
        return

    bind = op.get_bind()
    chats_table = table(
        "chats",
        column("chat_id", sa.Text()),
        column("user_id", sa.Integer()),
    )

    rows = [{"chat_id": group_chat_id, "user_id": user_id} for user_id in USERNAME_TO_ID.values()]
    if rows:
        bind.execute(chats_table.insert(), rows)


def downgrade() -> None:
    op.drop_table("chats")
