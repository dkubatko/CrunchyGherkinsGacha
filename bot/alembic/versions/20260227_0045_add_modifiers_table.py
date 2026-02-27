"""Add modifiers table and extend sets/cards/modifier_counts

Revision ID: 0045
Revises: 0044
Create Date: 2026-02-27

Creates a ``modifiers`` table to store modifier keywords in the database,
extends ``sets`` with ``description`` and ``active`` columns, adds a
``modifier_id`` FK to ``cards`` and ``modifier_counts``, seeds the
``modifiers`` table from existing YAML files, and backfills the FK columns
on ``cards`` and ``modifier_counts``.
"""

import os
import datetime
from pathlib import Path

import yaml
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260227_0045"
down_revision = "20260217_0044"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Path to YAML modifier files (relative to the bot/ directory which is the
# Alembic working directory).
# ---------------------------------------------------------------------------
_MODIFIERS_BASE_DIR = Path(__file__).resolve().parents[2] / "data" / "modifiers"


def _read_yaml(path: Path) -> dict:
    """Read a YAML file, skipping leading comment lines."""
    raw = path.read_text(encoding="utf-8")
    body_lines = []
    header_phase = True
    for line in raw.splitlines():
        if header_phase and (line.strip().startswith("#") or not line.strip()):
            continue
        header_phase = False
        body_lines.append(line)
    body = "\n".join(body_lines).lstrip()
    doc = yaml.safe_load(body) if body else {}
    return doc if isinstance(doc, dict) else {}


def _collect_modifiers_from_yaml() -> list[dict]:
    """Parse all season YAML directories and return a flat list of modifier rows."""
    rows: list[dict] = []
    now = datetime.datetime.utcnow().isoformat()

    if not _MODIFIERS_BASE_DIR.is_dir():
        return rows

    for season_dir in sorted(_MODIFIERS_BASE_DIR.iterdir()):
        if not season_dir.is_dir() or not season_dir.name.startswith("season_"):
            continue

        try:
            season_id = int(season_dir.name.split("_", 1)[1])
        except (ValueError, IndexError):
            continue

        for yaml_file in sorted(season_dir.glob("*.yaml")):
            doc = _read_yaml(yaml_file)
            if not doc or not doc.get("active", True):
                continue

            set_id = doc.get("id")
            if set_id is None:
                continue

            # Also capture set-level metadata for the sets table update
            set_description = doc.get("description", "")

            rarities = doc.get("rarities")
            if not isinstance(rarities, list):
                continue

            for rarity_entry in rarities:
                if not isinstance(rarity_entry, dict):
                    continue
                rarity_name = rarity_entry.get("name")
                if not rarity_name:
                    continue
                modifiers = rarity_entry.get("modifiers") or []
                for mod in modifiers:
                    if mod is None:
                        continue
                    mod_str = str(mod).strip()
                    if not mod_str:
                        continue
                    rows.append(
                        {
                            "set_id": set_id,
                            "season_id": season_id,
                            "name": mod_str,
                            "rarity": rarity_name,
                            "created_at": now,
                        }
                    )

    return rows


def _collect_set_descriptions_from_yaml() -> dict[tuple[int, int], str]:
    """Return a mapping of (set_id, season_id) → description from YAML."""
    descriptions: dict[tuple[int, int], str] = {}

    if not _MODIFIERS_BASE_DIR.is_dir():
        return descriptions

    for season_dir in sorted(_MODIFIERS_BASE_DIR.iterdir()):
        if not season_dir.is_dir() or not season_dir.name.startswith("season_"):
            continue
        try:
            season_id = int(season_dir.name.split("_", 1)[1])
        except (ValueError, IndexError):
            continue

        for yaml_file in sorted(season_dir.glob("*.yaml")):
            doc = _read_yaml(yaml_file)
            if not doc:
                continue
            set_id = doc.get("id")
            if set_id is None:
                continue
            descriptions[(set_id, season_id)] = doc.get("description", "")

    return descriptions


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Add description and active columns to sets
    # ------------------------------------------------------------------
    with op.batch_alter_table("sets") as batch_op:
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1"))
        )

    # Backfill set descriptions from YAML
    set_descriptions = _collect_set_descriptions_from_yaml()
    for (set_id, season_id), description in set_descriptions.items():
        if description:
            op.execute(
                sa.text(
                    "UPDATE sets SET description = :desc WHERE id = :sid AND season_id = :ssid"
                ).bindparams(desc=description, sid=set_id, ssid=season_id)
            )

    # ------------------------------------------------------------------
    # 2. Create modifiers table
    # ------------------------------------------------------------------
    op.create_table(
        "modifiers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("set_id", sa.Integer(), nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("rarity", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["set_id", "season_id"],
            ["sets.id", "sets.season_id"],
            name="fk_modifiers_set_season",
        ),
    )
    op.create_index("idx_modifiers_set_season", "modifiers", ["set_id", "season_id"])
    op.create_index("idx_modifiers_rarity", "modifiers", ["rarity"])
    op.create_index("idx_modifiers_name", "modifiers", ["name"])

    # ------------------------------------------------------------------
    # 3. Seed modifiers from YAML
    # ------------------------------------------------------------------
    modifier_rows = _collect_modifiers_from_yaml()
    if modifier_rows:
        modifiers_table = sa.table(
            "modifiers",
            sa.column("set_id", sa.Integer),
            sa.column("season_id", sa.Integer),
            sa.column("name", sa.Text),
            sa.column("rarity", sa.Text),
            sa.column("created_at", sa.Text),
        )
        op.bulk_insert(modifiers_table, modifier_rows)

    # ------------------------------------------------------------------
    # 4. Add modifier_id to cards and create index
    # ------------------------------------------------------------------
    with op.batch_alter_table("cards") as batch_op:
        batch_op.add_column(sa.Column("modifier_id", sa.Integer(), nullable=True))
        batch_op.create_index("idx_cards_modifier_id", ["modifier_id"])
        batch_op.create_foreign_key("fk_cards_modifier_id", "modifiers", ["modifier_id"], ["id"])

    # Backfill modifier_id on cards by matching (modifier, set_id, season_id)
    op.execute(
        sa.text(
            """
            UPDATE cards
            SET modifier_id = (
                SELECT m.id
                FROM modifiers m
                WHERE m.name = cards.modifier
                  AND m.set_id = cards.set_id
                  AND m.season_id = cards.season_id
                LIMIT 1
            )
            WHERE cards.set_id IS NOT NULL
            """
        )
    )

    # ------------------------------------------------------------------
    # 5. Add modifier_id to modifier_counts and create index
    # ------------------------------------------------------------------
    with op.batch_alter_table("modifier_counts") as batch_op:
        batch_op.add_column(sa.Column("modifier_id", sa.Integer(), nullable=True))
        batch_op.create_index("idx_modifier_counts_modifier_id", ["modifier_id"])
        batch_op.create_foreign_key(
            "fk_modifier_counts_modifier_id", "modifiers", ["modifier_id"], ["id"]
        )

    # Backfill modifier_id on modifier_counts by matching (modifier, season_id)
    op.execute(
        sa.text(
            """
            UPDATE modifier_counts
            SET modifier_id = (
                SELECT m.id
                FROM modifiers m
                WHERE m.name = modifier_counts.modifier
                  AND m.season_id = modifier_counts.season_id
                LIMIT 1
            )
            """
        )
    )


def downgrade() -> None:
    # Drop modifier_id from modifier_counts
    with op.batch_alter_table("modifier_counts") as batch_op:
        batch_op.drop_constraint("fk_modifier_counts_modifier_id", type_="foreignkey")
        batch_op.drop_index("idx_modifier_counts_modifier_id")
        batch_op.drop_column("modifier_id")

    # Drop modifier_id from cards
    with op.batch_alter_table("cards") as batch_op:
        batch_op.drop_constraint("fk_cards_modifier_id", type_="foreignkey")
        batch_op.drop_index("idx_cards_modifier_id")
        batch_op.drop_column("modifier_id")

    # Drop modifiers table
    op.drop_index("idx_modifiers_name", table_name="modifiers")
    op.drop_index("idx_modifiers_rarity", table_name="modifiers")
    op.drop_index("idx_modifiers_set_season", table_name="modifiers")
    op.drop_table("modifiers")

    # Remove description and active from sets
    with op.batch_alter_table("sets") as batch_op:
        batch_op.drop_column("active")
        batch_op.drop_column("description")
