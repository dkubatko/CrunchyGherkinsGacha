"""Add season_id to sets table with composite primary key

Revision ID: 20251227_0037
Revises: 20251227_0036
Create Date: 2025-12-27 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251227_0037"
down_revision = "20251227_0036"
branch_labels = None
depends_on = None

# Default season for existing sets
DEFAULT_SEASON_ID = 0


def upgrade() -> None:
    """Add season_id column to sets table and change to composite primary key."""
    # SQLite does not support ALTER TABLE for changing primary keys,
    # so we need to recreate the table with the new schema.

    conn = op.get_bind()

    # 0. Clean up any leftover temp table from a failed previous run
    conn.execute(sa.text("DROP TABLE IF EXISTS sets_new"))

    # 1. Create new table with composite primary key
    op.create_table(
        "sets_new",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False, server_default=str(DEFAULT_SEASON_ID)),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", "season_id"),
    )

    # 2. Copy data from old table, setting season_id to default
    conn.execute(
        sa.text(
            f"INSERT INTO sets_new (id, season_id, name) "
            f"SELECT id, {DEFAULT_SEASON_ID}, name FROM sets"
        )
    )

    # 3. Drop old table
    op.drop_table("sets")

    # 4. Rename new table to sets
    op.rename_table("sets_new", "sets")

    # 5. Update cards foreign key to use composite key
    # batch_alter_table recreates the table, so we just need to define the new FK
    # The old FK will be dropped automatically when the table is recreated
    with op.batch_alter_table(
        "cards",
        recreate="always",  # Force table recreation to ensure FK is updated
    ) as batch_op:
        # Add new composite FK constraint (old FK is dropped during recreation)
        batch_op.create_foreign_key(
            "fk_cards_set_season",
            "sets",
            ["set_id", "season_id"],
            ["id", "season_id"],
        )


def downgrade() -> None:
    """Revert sets table to single primary key."""
    # 1. Drop composite FK from cards
    with op.batch_alter_table("cards") as batch_op:
        batch_op.drop_constraint("fk_cards_set_season", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_cards_set_id_sets",
            "sets",
            ["set_id"],
            ["id"],
        )

    # 2. Recreate sets table with single primary key
    op.create_table(
        "sets_new",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # 3. Copy data (ignoring season_id)
    conn = op.get_bind()
    conn.execute(sa.text("INSERT OR IGNORE INTO sets_new (id, name) " "SELECT id, name FROM sets"))

    # 4. Drop old table
    op.drop_table("sets")

    # 5. Rename new table
    op.rename_table("sets_new", "sets")
