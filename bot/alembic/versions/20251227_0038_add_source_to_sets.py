"""Add source column to sets table

Revision ID: 20251227_0038
Revises: 20251227_0037
Create Date: 2025-12-27 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251227_0038"
down_revision = "20251227_0037"
branch_labels = None
depends_on = None

# Default source for existing sets (qualifies for any source)
DEFAULT_SOURCE = "all"


def upgrade() -> None:
    """Add source column to sets table with default 'all'."""
    # SQLite does not support ALTER TABLE ADD COLUMN with constraints easily,
    # so we recreate the table with the new schema.

    conn = op.get_bind()

    # 0. Clean up any leftover temp table from a failed previous run
    conn.execute(sa.text("DROP TABLE IF EXISTS sets_new"))

    # 1. Create new table with source column
    op.create_table(
        "sets_new",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default=DEFAULT_SOURCE),
        sa.PrimaryKeyConstraint("id", "season_id"),
    )

    # 2. Copy data from old table, setting source to default
    conn.execute(
        sa.text(
            f"INSERT INTO sets_new (id, season_id, name, source) "
            f"SELECT id, season_id, name, '{DEFAULT_SOURCE}' FROM sets"
        )
    )

    # 3. Drop old table
    op.drop_table("sets")

    # 4. Rename new table to sets
    op.rename_table("sets_new", "sets")


def downgrade() -> None:
    """Remove source column from sets table."""
    conn = op.get_bind()

    # 0. Clean up any leftover temp table from a failed previous run
    conn.execute(sa.text("DROP TABLE IF EXISTS sets_old"))

    # 1. Create table without source column
    op.create_table(
        "sets_old",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", "season_id"),
    )

    # 2. Copy data from current table (dropping source column)
    conn.execute(
        sa.text(
            "INSERT INTO sets_old (id, season_id, name) " "SELECT id, season_id, name FROM sets"
        )
    )

    # 3. Drop current table
    op.drop_table("sets")

    # 4. Rename old table to sets
    op.rename_table("sets_old", "sets")
