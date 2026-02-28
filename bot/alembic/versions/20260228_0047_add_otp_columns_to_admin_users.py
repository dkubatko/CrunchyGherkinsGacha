"""Add OTP columns to admin_users table

Revision ID: 0047
Revises: 0046
Create Date: 2026-02-28

Stores OTP code and expiry in the database so that all gunicorn workers
share the same OTP state, fixing the 'no OTP pending' error on first login.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260228_0047"
down_revision = "20260227_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("admin_users", sa.Column("otp_code", sa.Text, nullable=True))
    op.add_column("admin_users", sa.Column("otp_expires_at", sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column("admin_users", "otp_expires_at")
    op.drop_column("admin_users", "otp_code")
