"""Add locked field to cards table

Revision ID: 20251001_0018
Revises: 20251001_0017
Create Date: 2025-10-01 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251001_0018"
down_revision = "20251001_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add locked column to cards table with default value of False
    with op.batch_alter_table("cards", schema=None) as batch_op:
        batch_op.add_column(sa.Column("locked", sa.Boolean(), nullable=False, server_default="0"))

    # Backfill existing cards with locked=False (the server_default handles this automatically)
    # No explicit backfill needed as the column is created with server_default="0" (False)


def downgrade() -> None:
    with op.batch_alter_table("cards", schema=None) as batch_op:
        batch_op.drop_column("locked")
