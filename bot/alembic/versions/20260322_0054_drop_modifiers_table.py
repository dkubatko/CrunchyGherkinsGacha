"""Drop modifiers table and related FK/index from cards

Revision ID: 20260322_0054
Revises: 20260321_0053
Create Date: 2026-03-22

Removes the legacy modifier system as part of the Gacha 2.0 final cleanup
(Step 10).  The aspect_definitions table fully replaces modifiers.

Changes:
  - Drop FK constraint on cards.modifier_id → modifiers.id
  - Drop idx_16517_idx_cards_modifier_id index
  - Drop the modifier_id column from cards
  - Drop the modifiers table (including its FK to sets and all indexes)
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260322_0054"
down_revision = "20260321_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop the FK from cards.modifier_id → modifiers.id
    op.drop_constraint("cards_modifier_id_fkey", "cards", type_="foreignkey")

    # 2. Drop the index on cards.modifier_id
    #    (pgloader SQLite→PG migration added idx_16517_ prefix)
    op.drop_index("idx_16517_idx_cards_modifier_id", table_name="cards")

    # 3. Drop the modifier_id column from cards
    op.drop_column("cards", "modifier_id")

    # 4. Drop the modifiers table (cascade drops its own indexes & FK to sets)
    op.drop_table("modifiers")


def downgrade() -> None:
    # Re-create the modifiers table
    op.execute(
        """
        CREATE TABLE modifiers (
            id BIGSERIAL PRIMARY KEY,
            set_id BIGINT NOT NULL,
            season_id BIGINT NOT NULL,
            name TEXT NOT NULL,
            rarity TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE,
            CONSTRAINT fk_modifiers_set_season
                FOREIGN KEY (set_id, season_id) REFERENCES sets(id, season_id)
        )
        """
    )
    op.create_index("idx_modifiers_set_season", "modifiers", ["set_id", "season_id"])
    op.create_index("idx_modifiers_rarity", "modifiers", ["rarity"])
    op.create_index("idx_modifiers_name", "modifiers", ["name"])

    # Re-create the modifier_id column on cards
    op.add_column("cards", sa.Column("modifier_id", sa.BigInteger(), nullable=True))

    # Re-create the index on cards.modifier_id
    op.create_index("idx_cards_modifier_id", "cards", ["modifier_id"])

    # Re-create the FK from cards.modifier_id → modifiers.id
    op.create_foreign_key("cards_modifier_id_fkey", "cards", "modifiers", ["modifier_id"], ["id"])
