"""Create users table and seed with known usernames

Revision ID: 20240924_0004
Revises: 20240924_0003
Create Date: 2025-09-24 01:15:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import column, table

# revision identifiers, used by Alembic.
revision = "20240924_0004"
down_revision = "20240924_0003"
branch_labels = None
depends_on = None

USERNAME_TO_ID = {
    "krypthos": 1101242859,
    "brvsnshn": 305677569,
    "sonyabkim": 488359360,
    "matulka": 138354478,
    "maxelnot": 444838873,
    "imkht": 424292432,
    "max_zubatov": 487831762,
    "gabe_mkh": 1093842515,
    "yokocookie": 1395886306,
}


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("username", sa.Text(), nullable=False, unique=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("profile_imageb64", sa.Text(), nullable=True),
    )

    users_table = table(
        "users",
        column("user_id", sa.Integer()),
        column("username", sa.Text()),
    )
    rows = [{"user_id": uid, "username": username} for username, uid in USERNAME_TO_ID.items()]
    if rows:
        op.bulk_insert(users_table, rows)


def downgrade() -> None:
    op.drop_table("users")
