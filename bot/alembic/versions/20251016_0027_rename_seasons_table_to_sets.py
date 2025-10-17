"""Rename seasons table to sets

Revision ID: 20251016_0027
Revises: 20251016_0026
Create Date: 2025-10-16 00:30:00.000000

"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251016_0027"
down_revision = "20251016_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename the seasons table to sets."""
    op.rename_table("seasons", "sets")


def downgrade() -> None:
    """Restore the sets table name back to seasons."""
    op.rename_table("sets", "seasons")
