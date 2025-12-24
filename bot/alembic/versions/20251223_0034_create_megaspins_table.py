"""Create megaspins table to track spins until next megaspin

Revision ID: 20251223_0034
Revises: 20251223_0033
Create Date: 2024-12-23 10:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251223_0034"
down_revision = "20251223_0033"
branch_labels = None
depends_on = None

# Number of regular spins required for a megaspin (default value at migration time)
SPINS_FOR_MEGASPIN = 100


def upgrade() -> None:
    """Create megaspins table to track spins until next megaspin."""
    op.create_table(
        "megaspins",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column(
            "spins_until_megaspin",
            sa.Integer(),
            nullable=False,
            server_default=sa.text(str(SPINS_FOR_MEGASPIN)),
        ),
        sa.Column("megaspin_available", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("user_id", "chat_id"),
    )


def downgrade() -> None:
    """Drop the megaspins table."""
    op.drop_table("megaspins")
