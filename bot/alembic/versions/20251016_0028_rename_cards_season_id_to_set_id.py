"""Rename cards.season_id column to set_id

Revision ID: 20251016_0028
Revises: 20251016_0027
Create Date: 2025-10-16 00:35:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251016_0028"
down_revision = "20251016_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename cards.season_id to set_id."""
    with op.batch_alter_table("cards") as batch:
        batch.alter_column("season_id", new_column_name="set_id")


def downgrade() -> None:
    """Revert cards.set_id back to season_id."""
    with op.batch_alter_table("cards") as batch:
        batch.alter_column("set_id", new_column_name="season_id")
