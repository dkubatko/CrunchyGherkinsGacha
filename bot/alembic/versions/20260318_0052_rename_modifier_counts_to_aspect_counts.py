"""Rename modifier_counts table to aspect_counts

Revision ID: 20260318_0052
Revises: 20260317_0051
Create Date: 2026-03-18

Renames:
  - Table: modifier_counts → aspect_counts
  - Column: modifier → name
  - Column: modifier_id → definition_id
  - Indexes and FK constraint updated accordingly

Also re-points the FK from modifiers.id to aspect_definitions.id,
backfilling definition_id values by joining on modifier id (the
aspect_definitions table was seeded from modifiers in migration 0051,
so the IDs match 1:1).
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260318_0052"
down_revision = "20260317_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Drop the existing FK constraint pointing to modifiers.id
    # ------------------------------------------------------------------
    with op.batch_alter_table("modifier_counts") as batch_op:
        batch_op.drop_constraint("modifier_counts_modifier_id_fkey", type_="foreignkey")

    # ------------------------------------------------------------------
    # 2. Rename the table
    # ------------------------------------------------------------------
    op.rename_table("modifier_counts", "aspect_counts")

    # ------------------------------------------------------------------
    # 3. Rename columns
    # ------------------------------------------------------------------
    op.alter_column("aspect_counts", "modifier", new_column_name="name")
    op.alter_column("aspect_counts", "modifier_id", new_column_name="definition_id")

    # ------------------------------------------------------------------
    # 4. Drop old indexes and create new ones with updated names
    #    (Original SQLite→PG migration added `idx_16523_` prefix to all
    #    index names; use the actual names from the database.)
    # ------------------------------------------------------------------
    op.drop_index("idx_16523_idx_modifier_counts_chat_season", table_name="aspect_counts")
    op.drop_index("idx_16523_idx_modifier_counts_modifier_id", table_name="aspect_counts")

    op.create_index("idx_aspect_counts_chat_season", "aspect_counts", ["chat_id", "season_id"])
    op.create_index("idx_aspect_counts_definition_id", "aspect_counts", ["definition_id"])

    # ------------------------------------------------------------------
    # 5. Backfill: definition_id values already match aspect_definitions.id
    #    (migration 0051 copied modifiers rows with the same IDs), so the
    #    existing values are correct. Just add the new FK constraint.
    # ------------------------------------------------------------------
    with op.batch_alter_table("aspect_counts") as batch_op:
        batch_op.create_foreign_key(
            "fk_aspect_counts_definition_id",
            "aspect_definitions",
            ["definition_id"],
            ["id"],
        )


def downgrade() -> None:
    # Drop new FK
    with op.batch_alter_table("aspect_counts") as batch_op:
        batch_op.drop_constraint("fk_aspect_counts_definition_id", type_="foreignkey")

    # Drop new indexes
    op.drop_index("idx_aspect_counts_definition_id", table_name="aspect_counts")
    op.drop_index("idx_aspect_counts_chat_season", table_name="aspect_counts")

    # Rename columns back
    op.alter_column("aspect_counts", "name", new_column_name="modifier")
    op.alter_column("aspect_counts", "definition_id", new_column_name="modifier_id")

    # Rename table back
    op.rename_table("aspect_counts", "modifier_counts")

    # Recreate old indexes (with original SQLite→PG prefixed names)
    op.create_index(
        "idx_16523_idx_modifier_counts_chat_season",
        "modifier_counts",
        ["chat_id", "season_id"],
    )
    op.create_index(
        "idx_16523_idx_modifier_counts_modifier_id",
        "modifier_counts",
        ["modifier_id"],
    )

    # Restore old FK
    with op.batch_alter_table("modifier_counts") as batch_op:
        batch_op.create_foreign_key(
            "modifier_counts_modifier_id_fkey",
            "modifiers",
            ["modifier_id"],
            ["id"],
        )
