"""Add equip_sessions table

Revision ID: 20260326_0055
Revises: 20260322_0054
Create Date: 2026-03-26

Adds the equip_sessions table for persisting pending equip confirmations
across the bot command and miniapp equip-initiate flows.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260326_0055"
down_revision = "20260322_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equip_sessions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("chat_id", sa.Text, nullable=False),
        sa.Column("aspect_id", sa.BigInteger, nullable=False),
        sa.Column("card_id", sa.BigInteger, nullable=False),
        sa.Column("name_prefix", sa.Text, nullable=False),
        sa.Column("aspect_name", sa.Text, nullable=False),
        sa.Column("aspect_rarity", sa.Text, nullable=False),
        sa.Column("card_title", sa.Text, nullable=False),
        sa.Column("new_title", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "chat_id", name="uq_equip_sessions_user_chat"),
    )
    op.create_index(
        "idx_equip_sessions_user_chat", "equip_sessions", ["user_id", "chat_id"]
    )


def downgrade() -> None:
    op.drop_table("equip_sessions")
