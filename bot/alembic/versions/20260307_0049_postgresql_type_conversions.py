"""PostgreSQL type conversions after pgloader migration

Revision ID: 20260307_0049
Revises: 20260228_0048
Create Date: 2026-03-07

Converts columns from their pgloader-transferred SQLite types to
PostgreSQL-native types. This migration must run AFTER pgloader has
loaded the SQLite data into PostgreSQL and `alembic stamp head` has
been executed on revision 20260228_0048.

Changes:
  - Rename image/icon columns (drop _b64 suffix since they become bytea)
  - text timestamps  → timestamptz
  - text date        → date
  - text JSON        → jsonb
  - text base64      → bytea  (via decode(col, 'base64'))
  - datetime (naive) → timestamptz  (assume UTC)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "20260307_0049"
down_revision = "20260228_0048"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rename(table: str, old: str, new: str) -> None:
    op.alter_column(table, old, new_column_name=new)


def _text_to_timestamptz(table: str, col: str, nullable: bool) -> None:
    """Convert a text column storing ISO-8601 strings to timestamptz."""
    op.alter_column(
        table,
        col,
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"{col}::timestamptz",
        nullable=nullable,
    )


def _datetime_to_timestamptz(table: str, col: str, nullable: bool) -> None:
    """Promote a naive timestamp (from pgloader) to timestamptz, assuming UTC."""
    op.alter_column(
        table,
        col,
        type_=sa.DateTime(timezone=True),
        postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        nullable=nullable,
    )


def _text_to_jsonb(table: str, col: str, nullable: bool) -> None:
    op.alter_column(
        table,
        col,
        type_=JSONB(),
        postgresql_using=f"{col}::jsonb",
        nullable=nullable,
    )


def _text_to_bytea(table: str, col: str, nullable: bool) -> None:
    """Convert a text column containing base64 data to bytea.

    Rows with invalid base64 (e.g. placeholder strings like "dummy")
    are NULLed out before the cast.
    """
    # NULL out any values that aren't valid base64 (length must be
    # divisible by 4 and contain only base64 chars).
    op.execute(
        sa.text(
            f"UPDATE {table} SET {col} = NULL "
            f"WHERE {col} IS NOT NULL AND ("
            f"  length({col}) % 4 != 0 OR "
            f"  {col} !~ '^[A-Za-z0-9+/\\n]*(={{0,2}})$'"
            f")"
        )
    )
    op.alter_column(
        table,
        col,
        type_=sa.LargeBinary(),
        postgresql_using=f"decode({col}, 'base64')",
        nullable=nullable,
    )


def _text_to_date(table: str, col: str, nullable: bool) -> None:
    op.alter_column(
        table,
        col,
        type_=sa.Date(),
        postgresql_using=f"{col}::date",
        nullable=nullable,
    )


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Column renames  (before type changes so USING clauses use new names)
    # ------------------------------------------------------------------

    # card_images: image_b64 → image, image_thumb_b64 → thumbnail
    _rename("card_images", "image_b64", "image")
    _rename("card_images", "image_thumb_b64", "thumbnail")

    # users: profile_imageb64 → profile_image, slot_iconb64 → slot_icon
    _rename("users", "profile_imageb64", "profile_image")
    _rename("users", "slot_iconb64", "slot_icon")

    # characters: imageb64 → image, slot_iconb64 → slot_icon
    _rename("characters", "imageb64", "image")
    _rename("characters", "slot_iconb64", "slot_icon")

    # achievements: icon_b64 → icon
    _rename("achievements", "icon_b64", "icon")

    # ------------------------------------------------------------------
    # 2. text → timestamptz  (columns that were Text in the SQLite ORM)
    # ------------------------------------------------------------------
    _text_to_timestamptz("cards", "created_at", nullable=True)
    _text_to_timestamptz("cards", "updated_at", nullable=True)
    _text_to_timestamptz("card_images", "image_updated_at", nullable=True)
    _text_to_timestamptz("user_rolls", "last_roll_timestamp", nullable=False)
    _text_to_timestamptz("rolled_cards", "created_at", nullable=False)
    _text_to_timestamptz("modifiers", "created_at", nullable=True)
    _text_to_timestamptz("admin_users", "created_at", nullable=False)

    # ------------------------------------------------------------------
    # 3. datetime (naive) → timestamptz  (columns that were DateTime
    #    without timezone in the old ORM; pgloader maps them to
    #    "timestamp without time zone")
    # ------------------------------------------------------------------
    _datetime_to_timestamptz("minesweeper_games", "started_timestamp", nullable=False)
    _datetime_to_timestamptz("minesweeper_games", "last_updated_timestamp", nullable=False)
    _datetime_to_timestamptz("rtb_games", "started_timestamp", nullable=False)
    _datetime_to_timestamptz("rtb_games", "last_updated_timestamp", nullable=False)
    _datetime_to_timestamptz("events", "timestamp", nullable=False)
    _datetime_to_timestamptz("user_achievements", "unlocked_at", nullable=False)

    # ------------------------------------------------------------------
    # 4. text → jsonb
    # ------------------------------------------------------------------
    _text_to_jsonb("minesweeper_games", "mine_positions", nullable=False)
    _text_to_jsonb("minesweeper_games", "claim_point_positions", nullable=False)

    # Drop the text default *before* casting to jsonb (PG can't auto-cast '[]'::text)
    op.alter_column("minesweeper_games", "revealed_cells", server_default=None)
    _text_to_jsonb("minesweeper_games", "revealed_cells", nullable=False)
    # Re-add as jsonb default
    op.alter_column(
        "minesweeper_games",
        "revealed_cells",
        server_default=sa.text("'[]'::jsonb"),
    )

    _text_to_jsonb("rtb_games", "card_ids", nullable=False)
    _text_to_jsonb("rtb_games", "card_rarities", nullable=False)
    _text_to_jsonb("rtb_games", "card_titles", nullable=False)
    _text_to_jsonb("events", "payload", nullable=True)

    # ------------------------------------------------------------------
    # 5. text (base64) → bytea  (columns were already renamed above)
    # ------------------------------------------------------------------
    _text_to_bytea("card_images", "image", nullable=True)
    _text_to_bytea("card_images", "thumbnail", nullable=True)
    _text_to_bytea("users", "profile_image", nullable=True)
    _text_to_bytea("users", "slot_icon", nullable=True)
    _text_to_bytea("characters", "image", nullable=False)
    _text_to_bytea("characters", "slot_icon", nullable=True)
    _text_to_bytea("achievements", "icon", nullable=True)

    # ------------------------------------------------------------------
    # 6. text → date
    # ------------------------------------------------------------------
    _text_to_date("spins", "last_bonus_date", nullable=True)


# ---------------------------------------------------------------------------
# Downgrade  (reverse all changes — intended for emergencies only)
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # 6. date → text
    op.alter_column(
        "spins",
        "last_bonus_date",
        type_=sa.Text(),
        postgresql_using="last_bonus_date::text",
        nullable=True,
    )

    # 5. bytea → text (encode back to base64)
    for table, col, nullable in [
        ("card_images", "image", True),
        ("card_images", "thumbnail", True),
        ("users", "profile_image", True),
        ("users", "slot_icon", True),
        ("characters", "image", False),
        ("characters", "slot_icon", True),
        ("achievements", "icon", True),
    ]:
        op.alter_column(
            table,
            col,
            type_=sa.Text(),
            postgresql_using=f"encode({col}, 'base64')",
            nullable=nullable,
        )

    # 4. jsonb → text
    for table, col, nullable in [
        ("minesweeper_games", "mine_positions", False),
        ("minesweeper_games", "claim_point_positions", False),
        ("minesweeper_games", "revealed_cells", False),
        ("rtb_games", "card_ids", False),
        ("rtb_games", "card_rarities", False),
        ("rtb_games", "card_titles", False),
        ("events", "payload", True),
    ]:
        op.alter_column(
            table,
            col,
            type_=sa.Text(),
            postgresql_using=f"{col}::text",
            nullable=nullable,
        )

    op.alter_column(
        "minesweeper_games",
        "revealed_cells",
        server_default="[]",
    )

    # 3. timestamptz → timestamp (naive) for originally-DateTime columns
    for table, col, nullable in [
        ("minesweeper_games", "started_timestamp", False),
        ("minesweeper_games", "last_updated_timestamp", False),
        ("rtb_games", "started_timestamp", False),
        ("rtb_games", "last_updated_timestamp", False),
        ("events", "timestamp", False),
        ("user_achievements", "unlocked_at", False),
    ]:
        op.alter_column(
            table,
            col,
            type_=sa.DateTime(),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
            nullable=nullable,
        )

    # 2. timestamptz → text for originally-Text columns
    for table, col, nullable in [
        ("cards", "created_at", True),
        ("cards", "updated_at", True),
        ("card_images", "image_updated_at", True),
        ("user_rolls", "last_roll_timestamp", False),
        ("rolled_cards", "created_at", False),
        ("modifiers", "created_at", True),
        ("admin_users", "created_at", False),
    ]:
        op.alter_column(
            table,
            col,
            type_=sa.Text(),
            postgresql_using=f"{col}::text",
            nullable=nullable,
        )

    # 1. Reverse column renames
    _rename("card_images", "image", "image_b64")
    _rename("card_images", "thumbnail", "image_thumb_b64")
    _rename("users", "profile_image", "profile_imageb64")
    _rename("users", "slot_icon", "slot_iconb64")
    _rename("characters", "image", "imageb64")
    _rename("characters", "slot_icon", "slot_iconb64")
    _rename("achievements", "icon", "icon_b64")
