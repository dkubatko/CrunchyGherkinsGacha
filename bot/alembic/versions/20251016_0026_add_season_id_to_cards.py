"""Add season_id to cards table

Revision ID: 20251016_0026
Revises: 20251016_0025
Create Date: 2025-10-16 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

CLASSIC_SEASON_ID = 0
CLASSIC_SEASON_NAME = "classic"

# revision identifiers, used by Alembic.
revision = "20251016_0026"
down_revision = "20251016_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add season_id column to cards table."""
    op.add_column("cards", sa.Column("season_id", sa.Integer(), nullable=True))

    conn = op.get_bind()

    seasons_table = sa.table(
        "seasons",
        sa.column("id", sa.Integer),
        sa.column("name", sa.Text),
    )
    cards_table = sa.table(
        "cards",
        sa.column("season_id", sa.Integer),
    )

    existing_classic = conn.execute(
        sa.select(seasons_table.c.id).where(seasons_table.c.id == CLASSIC_SEASON_ID)
    ).first()

    if existing_classic is None:
        conn.execute(
            sa.insert(seasons_table).values(id=CLASSIC_SEASON_ID, name=CLASSIC_SEASON_NAME)
        )

    conn.execute(
        sa.update(cards_table)
        .where(cards_table.c.season_id.is_(None))
        .values(season_id=CLASSIC_SEASON_ID)
    )


def downgrade() -> None:
    """Remove season_id column from cards table."""
    op.drop_column("cards", "season_id")
