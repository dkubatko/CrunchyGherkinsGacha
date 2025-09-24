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
    "user_1": 100000001,
    "user_2": 100000002,
    "user_3": 100000003,
    "user_4": 100000004,
    "user_5": 100000005,
    "user_6": 100000006,
    "user_7": 100000007,
    "user_8": 100000008,
    "user_9": 100000009,
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
