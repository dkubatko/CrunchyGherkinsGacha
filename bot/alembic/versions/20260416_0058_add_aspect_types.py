"""Add aspect_types table and type_id FK on aspect_definitions

Revision ID: 20260416_0058
Revises: 20260404_0057
Create Date: 2026-04-16

Adds a new aspect_types table for categorising aspects by type
(e.g., Location, Creature, Mood) and a nullable type_id FK column
on aspect_definitions pointing at the new table.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260416_0058"
down_revision = "20260404_0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "aspect_types",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "aspect_definitions",
        sa.Column("type_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_aspect_definitions_type",
        "aspect_definitions",
        "aspect_types",
        ["type_id"],
        ["id"],
    )
    op.create_index(
        "idx_aspect_definitions_type_id",
        "aspect_definitions",
        ["type_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_aspect_definitions_type_id", table_name="aspect_definitions")
    op.drop_constraint("fk_aspect_definitions_type", "aspect_definitions", type_="foreignkey")
    op.drop_column("aspect_definitions", "type_id")
    op.drop_table("aspect_types")
