"""Add description column to cards table

Revision ID: 0048
Revises: 20260228_0047
Create Date: 2026-02-28

Stores an optional user-provided description for unique cards,
used to persist creator context across card refreshes.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260228_0048"
down_revision = "20260228_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cards", sa.Column("description", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("cards", "description")
