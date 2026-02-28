"""Add admin_users table for dashboard authentication

Revision ID: 0046
Revises: 0045
Create Date: 2026-02-27

Creates the ``admin_users`` table used by the standalone admin dashboard.
Admin accounts are provisioned via ``tools/create_admin.py``; there is no
self-registration.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260227_0046"
down_revision = "20260227_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.Text, nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("telegram_user_id", sa.Integer, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_index("idx_admin_users_username", "admin_users", ["username"])


def downgrade() -> None:
    op.drop_index("idx_admin_users_username", table_name="admin_users")
    op.drop_table("admin_users")
