"""Create characters table for custom chat characters

Revision ID: 20241002_0009
Revises: 20241001_0008
Create Date: 2024-10-02 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20241002_0009"
down_revision = "20241001_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "characters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("image", sa.Text(), nullable=False),
    )

    # Create index for performance when querying by chat_id
    op.create_index("ix_characters_chat_id", "characters", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_characters_chat_id")
    op.drop_table("characters")
