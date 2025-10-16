"""Remove foreign key constraints from rolled_cards

Revision ID: 20251015_0024
Revises: 20251011_0023
Create Date: 2025-10-15 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "20251015_0024"
down_revision = "20251011_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    op.drop_index("ix_rolled_cards_original_roller_id", table_name="rolled_cards")

    op.create_table(
        "rolled_cards_tmp",
        sa.Column("roll_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("original_card_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("rerolled_card_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("original_roller_id", sa.Integer(), nullable=False),
        sa.Column("rerolled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("being_rerolled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attempted_by", sa.Text(), nullable=True),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    connection.execute(
        text(
            """
            INSERT INTO rolled_cards_tmp (
                roll_id,
                original_card_id,
                rerolled_card_id,
                created_at,
                original_roller_id,
                rerolled,
                being_rerolled,
                attempted_by,
                is_locked
            )
            SELECT
                roll_id,
                original_card_id,
                rerolled_card_id,
                created_at,
                original_roller_id,
                rerolled,
                being_rerolled,
                attempted_by,
                is_locked
            FROM rolled_cards
            """
        )
    )

    op.drop_table("rolled_cards")
    op.rename_table("rolled_cards_tmp", "rolled_cards")

    op.create_index(
        "ix_rolled_cards_original_roller_id",
        "rolled_cards",
        ["original_roller_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()

    op.drop_index("ix_rolled_cards_original_roller_id", table_name="rolled_cards")

    op.create_table(
        "rolled_cards_tmp",
        sa.Column("roll_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("original_card_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("rerolled_card_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("original_roller_id", sa.Integer(), nullable=False),
        sa.Column("rerolled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("being_rerolled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attempted_by", sa.Text(), nullable=True),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["original_card_id"], ["cards.id"], name="fk_rolled_cards_original"
        ),
        sa.ForeignKeyConstraint(
            ["rerolled_card_id"], ["cards.id"], name="fk_rolled_cards_rerolled"
        ),
    )

    connection.execute(
        text(
            """
            INSERT INTO rolled_cards_tmp (
                roll_id,
                original_card_id,
                rerolled_card_id,
                created_at,
                original_roller_id,
                rerolled,
                being_rerolled,
                attempted_by,
                is_locked
            )
            SELECT
                roll_id,
                original_card_id,
                rerolled_card_id,
                created_at,
                original_roller_id,
                rerolled,
                being_rerolled,
                attempted_by,
                is_locked
            FROM rolled_cards
            """
        )
    )

    op.drop_table("rolled_cards")
    op.rename_table("rolled_cards_tmp", "rolled_cards")

    op.create_index(
        "ix_rolled_cards_original_roller_id",
        "rolled_cards",
        ["original_roller_id"],
    )
