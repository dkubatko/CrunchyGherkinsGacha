"""Fix boolean columns and auto-increment sequences after pgloader migration

Revision ID: 20260307_0050
Revises: 20260307_0049
Create Date: 2026-03-07

pgloader mapped SQLite integer-backed booleans to bigint and did not
create sequences for auto-increment primary keys.  This migration:
  - Converts bigint boolean columns to native PostgreSQL boolean
  - Creates sequences for all autoincrement primary-key columns and
    wires them up as column defaults
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260307_0050"
down_revision = "20260307_0049"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bigint_to_bool(table: str, col: str, nullable: bool, default: bool) -> None:
    """Convert a bigint column (0/1) to native boolean (idempotent)."""
    # Check if the column is already boolean (from a previous partial run)
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :col"
        ),
        {"table": table, "col": col},
    ).scalar()
    if result == "boolean":
        return  # Already converted

    pg_default = "true" if default else "false"
    # Drop the old integer server default first — PG can't auto-cast '0'/'1' to boolean
    op.alter_column(table, col, server_default=None)
    op.alter_column(
        table,
        col,
        type_=sa.Boolean(),
        postgresql_using=f"{col}::int::boolean",
        nullable=nullable,
    )
    op.alter_column(table, col, server_default=sa.text(pg_default))


def _ensure_sequence(table: str, col: str) -> None:
    """Create a sequence for a primary-key column and attach it as the default.

    The sequence is initialised to MAX(col)+1 so that new inserts don't
    collide with existing rows.
    """
    seq_name = f"{table}_{col}_seq"

    # Create the sequence (IF NOT EXISTS to be safe)
    op.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))

    # Set the sequence value to the current max
    op.execute(
        sa.text(
            f"SELECT setval('{seq_name}', COALESCE((SELECT MAX({col}) FROM {table}), 0) + 1, false)"
        )
    )

    # Attach sequence as default for the column
    op.alter_column(
        table,
        col,
        server_default=sa.text(f"nextval('{seq_name}')"),
    )

    # Mark the sequence as owned by the column so it's dropped automatically
    op.execute(sa.text(f"ALTER SEQUENCE {seq_name} OWNED BY {table}.{col}"))


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. bigint → boolean  (SQLite stored bools as 0/1 integers)
    # ------------------------------------------------------------------
    _bigint_to_bool("cards", "locked", nullable=False, default=False)
    _bigint_to_bool("rolled_cards", "rerolled", nullable=False, default=False)
    _bigint_to_bool("rolled_cards", "being_rerolled", nullable=False, default=False)
    _bigint_to_bool("rolled_cards", "is_locked", nullable=False, default=False)
    _bigint_to_bool("megaspins", "megaspin_available", nullable=False, default=False)
    _bigint_to_bool("sets", "active", nullable=False, default=True)

    # ------------------------------------------------------------------
    # 2. Ensure auto-increment sequences exist for all PK columns
    # ------------------------------------------------------------------
    _ensure_sequence("cards", "id")
    _ensure_sequence("rolled_cards", "roll_id")
    _ensure_sequence("characters", "id")
    _ensure_sequence("minesweeper_games", "id")
    _ensure_sequence("rtb_games", "id")
    _ensure_sequence("events", "id")
    _ensure_sequence("modifiers", "id")
    _ensure_sequence("achievements", "id")
    _ensure_sequence("user_achievements", "id")
    _ensure_sequence("admin_users", "id")


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # 2. Drop sequences (revert defaults first)
    for table, col in [
        ("cards", "id"),
        ("rolled_cards", "roll_id"),
        ("characters", "id"),
        ("minesweeper_games", "id"),
        ("rtb_games", "id"),
        ("events", "id"),
        ("modifiers", "id"),
        ("achievements", "id"),
        ("user_achievements", "id"),
        ("admin_users", "id"),
    ]:
        seq_name = f"{table}_{col}_seq"
        op.alter_column(table, col, server_default=None)
        op.execute(sa.text(f"DROP SEQUENCE IF EXISTS {seq_name}"))

    # 1. boolean → bigint (drop boolean default first, then cast, then set integer default)
    for table, col, default in [
        ("cards", "locked", "0"),
        ("rolled_cards", "rerolled", "0"),
        ("rolled_cards", "being_rerolled", "0"),
        ("rolled_cards", "is_locked", "0"),
        ("megaspins", "megaspin_available", "0"),
        ("sets", "active", "1"),
    ]:
        op.alter_column(table, col, server_default=None)
        op.alter_column(
            table,
            col,
            type_=sa.BigInteger(),
            postgresql_using=f"{col}::int",
            nullable=False,
        )
        op.alter_column(table, col, server_default=sa.text(default))
