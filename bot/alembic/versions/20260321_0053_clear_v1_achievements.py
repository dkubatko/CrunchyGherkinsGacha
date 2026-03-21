"""Clear v1 achievements for Gacha 2.0 migration

Revision ID: 20260321_0053
Revises: 20260318_0052
Create Date: 2026-03-21

Deletes all rows from achievements and user_achievements tables as part of
the Gacha 2.0 migration. All 15 v1 achievement definitions have been removed
from code; a new achievement set will be introduced in a future update.
Tables and schema are preserved for reuse.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260321_0053"
down_revision = "20260318_0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Clear user_achievements first (FK references achievements)
    op.execute("DELETE FROM user_achievements")
    # Clear achievement definitions
    op.execute("DELETE FROM achievements")


def downgrade() -> None:
    # Achievement data cannot be automatically restored.
    # The ensure_achievements_registered() startup hook would re-sync
    # definitions from code, but v1 classes no longer exist.
    pass
