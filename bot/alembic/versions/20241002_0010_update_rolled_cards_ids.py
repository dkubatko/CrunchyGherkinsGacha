"""Add rerolled_card_id and rename card_id to original_card_id on rolled_cards

Revision ID: 20241002_0010
Revises: 20241002_0009
Create Date: 2024-10-02 12:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "20241002_0010"
down_revision = "20241002_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = {column["name"] for column in inspector.get_columns("rolled_cards")}
    foreign_keys = {
        fk["name"] for fk in inspector.get_foreign_keys("rolled_cards") if fk.get("name")
    }

    with op.batch_alter_table("rolled_cards") as batch_op:
        if "card_id" in columns and "original_card_id" not in columns:
            batch_op.alter_column("card_id", new_column_name="original_card_id")
            columns.remove("card_id")
            columns.add("original_card_id")

        if "rerolled_card_id" not in columns:
            batch_op.add_column(sa.Column("rerolled_card_id", sa.Integer(), nullable=True))
            columns.add("rerolled_card_id")

        if "fk_rolled_cards_rerolled_card_id_cards" not in foreign_keys:
            batch_op.create_foreign_key(
                "fk_rolled_cards_rerolled_card_id_cards",
                "cards",
                ["rerolled_card_id"],
                ["id"],
            )

    if "rerolled_card_id" in columns and "original_card_id" in columns:
        connection.execute(
            text(
                """
                UPDATE rolled_cards
                SET rerolled_card_id = original_card_id
                WHERE rerolled_card_id IS NULL
                """
            )
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        text(
            """
            UPDATE rolled_cards
            SET original_card_id = COALESCE(rerolled_card_id, original_card_id)
            """
        )
    )

    with op.batch_alter_table("rolled_cards") as batch_op:
        batch_op.drop_constraint("fk_rolled_cards_rerolled_card_id_cards", type_="foreignkey")
        batch_op.drop_column("rerolled_card_id")
        batch_op.alter_column("original_card_id", new_column_name="card_id")
