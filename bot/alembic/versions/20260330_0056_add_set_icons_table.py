"""Add set_icons table

Revision ID: 20260330_0056
Revises: 20260326_0055
Create Date: 2026-03-30

Adds the set_icons table to store slot machine icons for aspect sets,
separate from the main sets table to avoid overhead on large queries.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260330_0056"
down_revision = "20260326_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "set_icons",
        sa.Column("set_id", sa.BigInteger, nullable=False),
        sa.Column("season_id", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("icon", sa.LargeBinary, nullable=False),
        sa.ForeignKeyConstraint(
            ["set_id", "season_id"],
            ["sets.id", "sets.season_id"],
            name="fk_set_icons_set_season",
        ),
        sa.PrimaryKeyConstraint("set_id", "season_id"),
    )


def downgrade() -> None:
    op.drop_table("set_icons")
