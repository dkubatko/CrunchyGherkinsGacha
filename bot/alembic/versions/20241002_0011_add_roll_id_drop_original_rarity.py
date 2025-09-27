"""Introduce roll_id primary key and remove original_rarity from rolled_cards

Revision ID: 20241002_0011
Revises: 20241002_0010
Create Date: 2024-10-02 12:30:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "20241002_0011"
down_revision = "20241002_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    connection.execute(text("DROP TABLE IF EXISTS rolled_cards_new"))

    op.create_table(
        "rolled_cards_new",
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
            ["original_card_id"], ["cards.id"], name="fk_rolled_cards_new_original"
        ),
        sa.ForeignKeyConstraint(
            ["rerolled_card_id"], ["cards.id"], name="fk_rolled_cards_new_rerolled"
        ),
    )

    connection.execute(
        text(
            """
            INSERT INTO rolled_cards_new (
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
                original_card_id AS roll_id,
                original_card_id,
                rerolled_card_id,
                created_at,
                original_roller_id,
                rerolled,
                being_rerolled,
                attempted_by,
                is_locked
            FROM rolled_cards
            WHERE original_card_id IS NOT NULL
            """
        )
    )

    op.drop_table("rolled_cards")
    op.rename_table("rolled_cards_new", "rolled_cards")

    op.create_index(
        "ix_rolled_cards_original_roller_id",
        "rolled_cards",
        ["original_roller_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()

    op.drop_index("ix_rolled_cards_original_roller_id", table_name="rolled_cards")

    op.create_table(
        "rolled_cards_old",
        sa.Column("original_card_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("original_roller_id", sa.Integer(), nullable=False),
        sa.Column("rerolled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("being_rerolled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attempted_by", sa.Text(), nullable=True),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rerolled_card_id", sa.Integer(), nullable=True),
        sa.Column("original_rarity", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("original_card_id"),
        sa.ForeignKeyConstraint(
            ["original_card_id"], ["cards.id"], name="fk_rolled_cards_old_original"
        ),
        sa.ForeignKeyConstraint(
            ["rerolled_card_id"], ["cards.id"], name="fk_rolled_cards_old_rerolled"
        ),
    )

    connection.execute(
        text(
            """
            INSERT INTO rolled_cards_old (
                original_card_id,
                created_at,
                original_roller_id,
                rerolled,
                being_rerolled,
                attempted_by,
                is_locked,
                rerolled_card_id,
                original_rarity
            )
            SELECT
                original_card_id,
                created_at,
                original_roller_id,
                rerolled,
                being_rerolled,
                attempted_by,
                is_locked,
                rerolled_card_id,
                NULL
            FROM rolled_cards
            """
        )
    )

    op.drop_table("rolled_cards")
    op.rename_table("rolled_cards_old", "rolled_cards")

    op.create_index(
        "ix_rolled_cards_original_roller_id",
        "rolled_cards",
        ["original_roller_id"],
    )
