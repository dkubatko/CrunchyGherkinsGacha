"""Aspect schema foundation — new tables and column alterations for Gacha 2.0

Revision ID: 20260317_0051
Revises: 20260307_0050
Create Date: 2026-03-17

Creates the aspect system tables (aspect_definitions, owned_aspects,
aspect_images, card_aspects, rolled_aspects), alters cards.modifier to
nullable, adds cards.aspect_count, adds events.aspect_id, and backfills
aspect_definitions from the existing modifiers table.

All changes are additive — the app continues functioning as-is after
this migration.  No handlers, services, or API routes are wired yet.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260317_0051"
down_revision = "20260307_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Create aspect_definitions table (mirrors modifiers structure)
    # ------------------------------------------------------------------
    op.create_table(
        "aspect_definitions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("set_id", sa.BigInteger(), nullable=False),
        sa.Column("season_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("rarity", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["set_id", "season_id"],
            ["sets.id", "sets.season_id"],
            name="fk_aspect_definitions_set_season",
        ),
    )
    op.create_index(
        "idx_aspect_definitions_set_season", "aspect_definitions", ["set_id", "season_id"]
    )
    op.create_index("idx_aspect_definitions_rarity", "aspect_definitions", ["rarity"])
    op.create_index("idx_aspect_definitions_name", "aspect_definitions", ["name"])

    # Ensure auto-increment sequence exists for aspect_definitions
    op.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS aspect_definitions_id_seq"))
    op.execute(
        sa.text(
            "SELECT setval('aspect_definitions_id_seq', "
            "COALESCE((SELECT MAX(id) FROM aspect_definitions), 0) + 1, false)"
        )
    )
    op.alter_column(
        "aspect_definitions",
        "id",
        server_default=sa.text("nextval('aspect_definitions_id_seq')"),
    )

    # ------------------------------------------------------------------
    # 2. Backfill aspect_definitions from existing modifiers table
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            "INSERT INTO aspect_definitions (id, set_id, season_id, name, rarity, created_at) "
            "SELECT id, set_id, season_id, name, rarity, created_at FROM modifiers"
        )
    )
    # Re-sync the sequence after backfill
    op.execute(
        sa.text(
            "SELECT setval('aspect_definitions_id_seq', "
            "COALESCE((SELECT MAX(id) FROM aspect_definitions), 0) + 1, false)"
        )
    )

    # ------------------------------------------------------------------
    # 3. Create owned_aspects table
    # ------------------------------------------------------------------
    op.create_table(
        "owned_aspects",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "aspect_definition_id",
            sa.BigInteger(),
            sa.ForeignKey("aspect_definitions.id"),
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("owner", sa.Text(), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("season_id", sa.BigInteger(), nullable=False),
        sa.Column("rarity", sa.Text(), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("file_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_owned_aspects_chat_season", "owned_aspects", ["chat_id", "season_id"])
    op.create_index("idx_owned_aspects_user_season", "owned_aspects", ["user_id", "season_id"])
    op.create_index("idx_owned_aspects_owner_season", "owned_aspects", ["owner", "season_id"])
    op.create_index("idx_owned_aspects_rarity_season", "owned_aspects", ["rarity", "season_id"])
    op.create_index("idx_owned_aspects_file_id", "owned_aspects", ["file_id"])
    op.create_index("idx_owned_aspects_definition_id", "owned_aspects", ["aspect_definition_id"])

    # Ensure auto-increment sequence for owned_aspects
    op.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS owned_aspects_id_seq"))
    op.execute(
        sa.text(
            "SELECT setval('owned_aspects_id_seq', "
            "COALESCE((SELECT MAX(id) FROM owned_aspects), 0) + 1, false)"
        )
    )
    op.alter_column(
        "owned_aspects",
        "id",
        server_default=sa.text("nextval('owned_aspects_id_seq')"),
    )

    # ------------------------------------------------------------------
    # 4. Create aspect_images table (mirrors card_images pattern)
    # ------------------------------------------------------------------
    op.create_table(
        "aspect_images",
        sa.Column(
            "aspect_id",
            sa.BigInteger(),
            sa.ForeignKey("owned_aspects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("image", sa.LargeBinary(), nullable=True),
        sa.Column("thumbnail", sa.LargeBinary(), nullable=True),
        sa.Column("image_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_aspect_images_aspect_id", "aspect_images", ["aspect_id"])

    # ------------------------------------------------------------------
    # 5. Create card_aspects junction table
    # ------------------------------------------------------------------
    op.create_table(
        "card_aspects",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("card_id", sa.BigInteger(), sa.ForeignKey("cards.id"), nullable=False),
        sa.Column(
            "aspect_id",
            sa.BigInteger(),
            sa.ForeignKey("owned_aspects.id"),
            nullable=False,
        ),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("equipped_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("aspect_id", name="uq_card_aspects_aspect_id"),
        sa.UniqueConstraint("card_id", "order", name="uq_card_aspects_card_order"),
        sa.CheckConstraint('"order" BETWEEN 1 AND 5', name="ck_card_aspects_order_range"),
    )
    op.create_index("idx_card_aspects_card_id_order", "card_aspects", ["card_id", "order"])

    # Ensure auto-increment sequence for card_aspects
    op.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS card_aspects_id_seq"))
    op.execute(
        sa.text(
            "SELECT setval('card_aspects_id_seq', "
            "COALESCE((SELECT MAX(id) FROM card_aspects), 0) + 1, false)"
        )
    )
    op.alter_column(
        "card_aspects",
        "id",
        server_default=sa.text("nextval('card_aspects_id_seq')"),
    )

    # ------------------------------------------------------------------
    # 6. Create rolled_aspects table (mirrors rolled_cards, no FK constraints)
    # ------------------------------------------------------------------
    op.create_table(
        "rolled_aspects",
        sa.Column("roll_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("original_aspect_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("rerolled_aspect_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("original_roller_id", sa.BigInteger(), nullable=False),
        sa.Column("rerolled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("being_rerolled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("attempted_by", sa.Text(), nullable=True),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("original_rarity", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_rolled_aspects_original_roller_id", "rolled_aspects", ["original_roller_id"]
    )

    # Ensure auto-increment sequence for rolled_aspects
    op.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS rolled_aspects_roll_id_seq"))
    op.execute(
        sa.text(
            "SELECT setval('rolled_aspects_roll_id_seq', "
            "COALESCE((SELECT MAX(roll_id) FROM rolled_aspects), 0) + 1, false)"
        )
    )
    op.alter_column(
        "rolled_aspects",
        "roll_id",
        server_default=sa.text("nextval('rolled_aspects_roll_id_seq')"),
    )

    # ------------------------------------------------------------------
    # 7. Alter cards table: modifier nullable + aspect_count column
    # ------------------------------------------------------------------
    with op.batch_alter_table("cards") as batch_op:
        batch_op.alter_column("modifier", nullable=True)
        batch_op.add_column(
            sa.Column("aspect_count", sa.Integer(), nullable=False, server_default="0")
        )

    # ------------------------------------------------------------------
    # 8. Alter events table: add aspect_id column
    # ------------------------------------------------------------------
    with op.batch_alter_table("events") as batch_op:
        batch_op.add_column(sa.Column("aspect_id", sa.BigInteger(), nullable=True))

    op.create_index("idx_events_aspect_id", "events", ["aspect_id"])


def downgrade() -> None:
    # ------------------------------------------------------------------
    # Reverse in exact opposite order
    # ------------------------------------------------------------------

    # 8. Remove events.aspect_id
    op.drop_index("idx_events_aspect_id", table_name="events")
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_column("aspect_id")

    # 7. Restore cards columns
    with op.batch_alter_table("cards") as batch_op:
        batch_op.drop_column("aspect_count")
        batch_op.alter_column("modifier", nullable=False)

    # 6. Drop rolled_aspects
    op.drop_index("ix_rolled_aspects_original_roller_id", table_name="rolled_aspects")
    op.execute(sa.text("DROP SEQUENCE IF EXISTS rolled_aspects_roll_id_seq"))
    op.drop_table("rolled_aspects")

    # 5. Drop card_aspects
    op.drop_index("idx_card_aspects_card_id_order", table_name="card_aspects")
    op.execute(sa.text("DROP SEQUENCE IF EXISTS card_aspects_id_seq"))
    op.drop_table("card_aspects")

    # 4. Drop aspect_images
    op.drop_index("idx_aspect_images_aspect_id", table_name="aspect_images")
    op.drop_table("aspect_images")

    # 3. Drop owned_aspects
    op.drop_index("idx_owned_aspects_definition_id", table_name="owned_aspects")
    op.drop_index("idx_owned_aspects_file_id", table_name="owned_aspects")
    op.drop_index("idx_owned_aspects_rarity_season", table_name="owned_aspects")
    op.drop_index("idx_owned_aspects_owner_season", table_name="owned_aspects")
    op.drop_index("idx_owned_aspects_user_season", table_name="owned_aspects")
    op.drop_index("idx_owned_aspects_chat_season", table_name="owned_aspects")
    op.execute(sa.text("DROP SEQUENCE IF EXISTS owned_aspects_id_seq"))
    op.drop_table("owned_aspects")

    # 2. (Backfilled rows deleted with the table drop — nothing to undo)

    # 1. Drop aspect_definitions
    op.drop_index("idx_aspect_definitions_name", table_name="aspect_definitions")
    op.drop_index("idx_aspect_definitions_rarity", table_name="aspect_definitions")
    op.drop_index("idx_aspect_definitions_set_season", table_name="aspect_definitions")
    op.execute(sa.text("DROP SEQUENCE IF EXISTS aspect_definitions_id_seq"))
    op.drop_table("aspect_definitions")
