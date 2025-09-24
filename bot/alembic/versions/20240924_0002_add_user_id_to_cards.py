"""Add user_id to cards and backfill

Revision ID: 20240924_0002
Revises: 20240924_0001
Create Date: 2025-09-24 00:30:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20240924_0002"
down_revision = "20240924_0001"
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
    with op.batch_alter_table("cards", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))

    bind = op.get_bind()
    for username, user_id in USERNAME_TO_ID.items():
        bind.execute(
            sa.text("UPDATE cards SET user_id = :user_id WHERE owner = :owner"),
            {"user_id": user_id, "owner": username},
        )


def downgrade() -> None:
    with op.batch_alter_table("cards", schema=None) as batch_op:
        batch_op.drop_column("user_id")
