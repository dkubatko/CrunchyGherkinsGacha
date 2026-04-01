"""Backfill aspect_counts table from the events table.

Scans aspect-creation events (ROLL, REROLL, RECYCLE, CREATE, SPIN, MEGASPIN,
MINESWEEPER) and rebuilds aspect_counts from scratch.  Handles both
payload-based name extraction and aspect_id fallback lookup.
Card-only events (no aspect_name / no aspect_id) are skipped.

Usage:
    cd bot && python tools/backfill_aspect_counts.py
    cd bot && python tools/backfill_aspect_counts.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root is on sys.path for module imports
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

from sqlalchemy.orm import joinedload  # noqa: E402
from utils.session import get_session  # noqa: E402
from utils.models import (  # noqa: E402
    EventModel,
    AspectCountModel,
    OwnedAspectModel,
)
from settings.constants import CURRENT_SEASON  # noqa: E402

# Event type/outcome pairs that represent aspect creation (NOT card creation)
ASPECT_CREATION_EVENTS = {
    ("ROLL", "SUCCESS"),
    ("REROLL", "SUCCESS"),
    ("RECYCLE", "SUCCESS"),
    ("CREATE", "SUCCESS"),
    ("SPIN", "ASPECT_WIN"),
    ("MEGASPIN", "SUCCESS"),
    ("MEGASPIN", "ASPECT_WIN"),
    ("MINESWEEPER", "WON"),
}


def _resolve_aspect_name(event: EventModel, aspect_cache: dict) -> tuple[str | None, int | None]:
    """Extract aspect name and definition_id from an event.

    Only looks for aspect-specific payload fields (aspect_name, aspect_definition_id).
    Returns (name, definition_id) or (None, None) if unresolvable.
    """
    payload = event.payload or {}

    name = payload.get("aspect_name")
    definition_id = payload.get("aspect_definition_id")

    if name:
        return name, definition_id

    # Fallback: look up by aspect_id
    aspect_id = event.aspect_id
    if aspect_id and aspect_id in aspect_cache:
        cached = aspect_cache[aspect_id]
        return cached["name"], cached["definition_id"]

    return None, None


def backfill_aspect_counts(dry_run: bool = False) -> None:
    """Rebuild aspect_counts from the events table."""
    print("Loading aspect lookup cache...")
    aspect_cache: dict[int, dict] = {}
    def_season_cache: dict[int, int] = {}  # definition_id -> season_id
    with get_session() as session:
        aspects = (
            session.query(OwnedAspectModel)
            .options(joinedload(OwnedAspectModel.aspect_definition))
            .all()
        )
        for a in aspects:
            name = None
            def_id = None
            season = None
            if a.aspect_definition:
                name = a.aspect_definition.name
                def_id = a.aspect_definition.id
                season = a.aspect_definition.season_id
            elif a.custom_name:
                name = a.custom_name
            if name:
                aspect_cache[a.id] = {"name": name, "definition_id": def_id, "season_id": season}
            if def_id and season:
                def_season_cache[def_id] = season

    print(f"  Cached {len(aspect_cache)} owned aspects.")

    print("Querying creation events...")
    with get_session() as session:
        events = (
            session.query(EventModel)
            .filter(
                EventModel.event_type.in_([t[0] for t in ASPECT_CREATION_EVENTS]),
            )
            .all()
        )

    # Filter to matching (event_type, outcome) pairs
    events = [
        e for e in events
        if (e.event_type, e.outcome) in ASPECT_CREATION_EVENTS
    ]
    print(f"  Found {len(events)} creation events to process.")

    # Aggregate counts: (chat_id, season_id, name) -> {count, definition_id}
    counts: dict[tuple[str, int | None, str], dict] = defaultdict(
        lambda: {"count": 0, "definition_id": None}
    )
    skipped = 0
    for event in events:
        name, definition_id = _resolve_aspect_name(event, aspect_cache)
        if not name:
            skipped += 1
            continue

        # Determine season_id: payload → definition cache → CURRENT_SEASON
        season_id = (event.payload or {}).get("season_id")
        if season_id is None and definition_id:
            season_id = def_season_cache.get(definition_id)
        if season_id is None:
            cached = aspect_cache.get(getattr(event, "aspect_id", None) or 0)
            if cached:
                season_id = cached.get("season_id")
        if season_id is None:
            season_id = CURRENT_SEASON

        key = (str(event.chat_id), season_id, name)
        entry = counts[key]
        entry["count"] += 1
        if definition_id and not entry["definition_id"]:
            entry["definition_id"] = definition_id

    print(f"  Aggregated {len(counts)} unique (chat, season, name) combos ({skipped} events skipped).")

    if dry_run:
        print("\n[DRY RUN] Would upsert the following counts:")
        for (chat_id, season_id, name), data in sorted(counts.items()):
            print(
                f"  chat={chat_id} season={season_id} name={name!r} "
                f"count={data['count']} def_id={data['definition_id']}"
            )
        print(f"\nTotal: {len(counts)} rows.")
        return

    # Clear and rebuild
    print("Clearing existing aspect_counts...")
    with get_session(commit=True) as session:
        session.query(AspectCountModel).delete()

    print("Inserting new aspect counts...")
    inserted = 0
    with get_session(commit=True) as session:
        for (chat_id, season_id, name), data in counts.items():
            record = AspectCountModel(
                chat_id=str(chat_id),
                season_id=season_id,
                name=name,
                definition_id=data["definition_id"],
                count=data["count"],
            )
            session.add(record)
            inserted += 1

    print(f"Successfully inserted {inserted} aspect count records.")

    # Summary
    print("\nSummary by season:")
    season_totals: dict[int | None, int] = defaultdict(int)
    for (_, season_id, _), data in counts.items():
        season_totals[season_id] += data["count"]
    for sid, total in sorted(season_totals.items(), key=lambda x: (x[0] is None, x[0])):
        print(f"  Season {sid}: {total} total aspect creations")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill aspect_counts table from the events table."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be inserted without making changes.",
    )
    args = parser.parse_args()
    backfill_aspect_counts(dry_run=args.dry_run)


if __name__ == "__main__":
    main()

