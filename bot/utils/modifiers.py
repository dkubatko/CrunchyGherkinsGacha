"""Helpers for loading modifier keyword lists from YAML set files."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional, NamedTuple

import yaml

from settings.constants import CURRENT_SEASON

LOGGER = logging.getLogger(__name__)

_MODIFIERS_BASE_DIR = Path(__file__).resolve().parents[1] / "data" / "modifiers"
_RARITY_ORDER = ("Common", "Rare", "Epic", "Legendary")


def _get_modifiers_dir(season_id: Optional[int] = None) -> Path:
    """Get the modifiers directory for the specified season.

    Args:
        season_id: The season to load modifiers for. Defaults to CURRENT_SEASON.

    Returns:
        Path to the modifiers directory for the given season.
    """
    if season_id is None:
        season_id = CURRENT_SEASON
    return _MODIFIERS_BASE_DIR / f"season_{season_id}"


class ModifierWithSet(NamedTuple):
    """A modifier with its associated set ID, name, and source."""

    modifier: str
    set_id: int
    set_name: str = ""
    source: str = "all"


def load_modifiers_with_sets(
    sets: Optional[Iterable[str]] = None,
    sync_db: bool = True,
    season_id: Optional[int] = None,
) -> dict[str, list[ModifierWithSet]]:
    """Load modifier keywords grouped by rarity with set information.

    Args:
        sets: Optional list of set names to load. If None, loads all sets.
        sync_db: Whether to sync set metadata to the database.
        season_id: The season to load modifiers for. Defaults to CURRENT_SEASON.

    Returns:
        Dictionary mapping rarity names to lists of ModifierWithSet.
    """

    ensure_logging_initialized()
    resolved_season_id = season_id if season_id is not None else CURRENT_SEASON
    set_files = _discover_set_files(sets, season_id=resolved_season_id)
    combined: defaultdict[str, list[ModifierWithSet]] = defaultdict(list)
    cross_rarity_tracker: defaultdict[str, dict[str, str]] = defaultdict(dict)

    for set_name, file_path in set_files:
        set_modifiers = _process_set_file(
            set_name=set_name,
            file_path=file_path,
            sync_db=sync_db,
            cross_rarity_tracker=cross_rarity_tracker,
            season_id=resolved_season_id,
        )
        for rarity, modifiers in set_modifiers.items():
            combined[rarity].extend(modifiers)

    ordered = _deduplicate_and_order_modifiers(combined)
    _warn_cross_rarity_conflicts(cross_rarity_tracker)
    return ordered


def _process_set_file(
    set_name: str,
    file_path: Path,
    sync_db: bool,
    cross_rarity_tracker: dict[str, dict[str, str]],
    season_id: int,
) -> dict[str, list[ModifierWithSet]]:
    """Load, normalize, and optionally persist a single set file."""

    LOGGER.info("Loading modifiers from %s...", file_path.name)
    header, document = _read_yaml(file_path)
    if not isinstance(document, dict):
        raise ValueError(f"Expected mapping at top level in {file_path.name}")

    # Skip inactive sets (default to active if not specified)
    if not document.get("active", True):
        LOGGER.info("Skipping inactive set: %s", file_path.name)
        return {}

    set_id = document.get("id")
    if set_id is None:
        raise ValueError(f"Set file {file_path.name} must have an 'id' field")

    # Parse source field (defaults to "all" if not specified)
    source = document.get("source", "all")
    if source not in ("roll", "slots", "all"):
        raise ValueError(
            f"Set file {file_path.name} has invalid 'source' value '{source}'. "
            "Must be 'roll', 'slots', or 'all'."
        )

    # Get display name from document, falling back to filename-derived name
    set_display_name = document.get("set", set_name)

    if sync_db:
        _sync_set_metadata(set_id, document, set_name, season_id, source)

    payload = document.get("rarities")
    if not isinstance(payload, list):
        raise ValueError(f"Expected 'rarities' to be a list of entries in {file_path.name}")

    entries = _prepare_rarity_entries(payload)
    normalized_entries, mutated, modifiers_by_rarity = _normalize_rarity_entries(
        set_name=set_name,
        set_display_name=set_display_name,
        set_id=set_id,
        source=source,
        entries=entries,
        original_payload=payload,
        cross_rarity_tracker=cross_rarity_tracker,
    )

    if mutated:
        document["rarities"] = normalized_entries
        _write_yaml(file_path, header, document)

    return modifiers_by_rarity


def _sync_set_metadata(
    set_id: int, document: dict[str, Any], default_name: str, season_id: int, source: str
) -> None:
    """Upsert the set metadata, keeping logging noise consistent."""

    set_display_name = document.get("set", default_name)
    try:
        from utils.services import set_service

        set_service.upsert_set(set_id, set_display_name, season_id=season_id, source=source)
        LOGGER.info(
            "Synced set %s (id=%s, season=%s, source=%s) to database",
            set_display_name,
            set_id,
            season_id,
            source,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.warning("Failed to sync set %s to database: %s", default_name, exc)


def _normalize_rarity_entries(
    *,
    set_name: str,
    set_display_name: str,
    set_id: int,
    source: str,
    entries: list[dict[str, Any]],
    original_payload: list[dict[str, Any]],
    cross_rarity_tracker: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], bool, dict[str, list[ModifierWithSet]]]:
    """Normalize modifier lists, track duplicates, and prepare persistence."""

    mutated = False
    modifiers_by_rarity: defaultdict[str, list[ModifierWithSet]] = defaultdict(list)

    for entry in entries:
        rarity = entry.get("name")
        if not rarity:
            continue

        raw_modifiers = entry.get("modifiers", [])
        normalized, changed, duplicates = _normalize_modifiers(raw_modifiers)

        if duplicates:
            LOGGER.info(
                "Dropped duplicate modifiers for set %s rarity %s: %s",
                set_name,
                rarity,
                sorted(duplicates),
            )
        if changed:
            mutated = True

        entry["modifiers"] = normalized

        modifiers_for_rarity = modifiers_by_rarity[rarity]
        if normalized:
            modifiers_for_rarity.extend(
                ModifierWithSet(
                    modifier=modifier, set_id=set_id, set_name=set_display_name, source=source
                )
                for modifier in normalized
            )

        for modifier in normalized:
            _register_cross_rarity(cross_rarity_tracker, rarity, modifier)

    sorted_entries = _sort_rarity_entries(entries)
    if sorted_entries != original_payload:
        mutated = True

    # Return plain dict for callers; defaultdict is local convenience only.
    return sorted_entries, mutated, dict(modifiers_by_rarity)


def _register_cross_rarity(tracker: dict[str, dict[str, str]], rarity: str, modifier: str) -> None:
    """Track modifier usage so we can warn when the same keyword spans rarities."""

    key = modifier.casefold()
    tracker.setdefault(key, {})[rarity] = modifier


def _deduplicate_and_order_modifiers(
    combined: dict[str, list[ModifierWithSet]],
) -> dict[str, list[ModifierWithSet]]:
    """Remove duplicate modifiers across sets and order the result by rarity."""

    aggregated: dict[str, list[ModifierWithSet]] = {}
    for rarity, modifiers in combined.items():
        seen: dict[str, ModifierWithSet] = {}
        duplicates: set[str] = set()

        for mod_with_set in modifiers:
            key = mod_with_set.modifier.casefold()
            if key in seen:
                duplicates.add(mod_with_set.modifier)
                continue
            seen[key] = mod_with_set

        if duplicates:
            LOGGER.info(
                "Dropped duplicate modifiers across sets for rarity %s: %s",
                rarity,
                sorted(duplicates),
            )

        aggregated[rarity] = [seen[key] for key in sorted(seen)]

    ordered: dict[str, list[ModifierWithSet]] = {}
    for rarity in _RARITY_ORDER:
        ordered[rarity] = aggregated.pop(rarity, [])

    for rarity in sorted(aggregated):
        ordered[rarity] = aggregated[rarity]

    return ordered


def _warn_cross_rarity_conflicts(tracker: dict[str, dict[str, str]]) -> None:
    """Emit warnings when a modifier appears in multiple rarity buckets."""

    rarity_rank = {name: index for index, name in enumerate(_RARITY_ORDER)}

    for rarity_map in tracker.values():
        if len(rarity_map) <= 1:
            continue

        sample_value = next(iter(rarity_map.values()))
        rarities_list = ", ".join(
            sorted(rarity_map, key=lambda rarity: rarity_rank.get(rarity, float("inf")))
        )
        LOGGER.warning(
            "Modifier '%s' appears in multiple rarities: %s",
            sample_value,
            rarities_list,
        )


def ensure_logging_initialized() -> None:
    """Set up a basic handler so modifier logs surface during early imports."""

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )

    if LOGGER.level == logging.NOTSET:
        LOGGER.setLevel(logging.INFO)


def _discover_set_files(
    sets: Optional[Iterable[str]],
    season_id: Optional[int] = None,
) -> list[tuple[str, Path]]:
    """Discover set files for the specified season.

    Args:
        sets: Optional list of set names to load. If None, loads all sets.
        season_id: The season to load modifiers for. Defaults to CURRENT_SEASON.

    Returns:
        List of (set_name, file_path) tuples.
    """
    modifiers_dir = _get_modifiers_dir(season_id)
    if not modifiers_dir.is_dir():
        raise FileNotFoundError(f"Modifiers directory not found at {modifiers_dir}")
    if sets is None:
        files = sorted(modifiers_dir.glob("*.yaml"))
        return [(path.stem, path) for path in files]

    if isinstance(sets, str):
        set_names = [sets]
    else:
        set_names = list(dict.fromkeys(sets))

    result: list[tuple[str, Path]] = []
    for name in set_names:
        path = modifiers_dir / f"{name}.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"Unknown modifiers set '{name}' at {path}")
        result.append((name, path))
    return result


def _read_yaml(path: Path) -> tuple[str, dict]:
    raw = path.read_text(encoding="utf-8")
    header_lines: list[str] = []
    body_lines: list[str] = []
    header_phase = True
    for line in raw.splitlines():
        if header_phase and (line.strip().startswith("#") or not line.strip()):
            header_lines.append(line)
            continue
        header_phase = False
        body_lines.append(line)

    header = "\n".join(header_lines).rstrip()
    body = "\n".join(body_lines).lstrip()

    document = yaml.safe_load(body) if body else {}
    if document is None:
        document = {}
    if not isinstance(document, dict):
        raise ValueError(f"Unexpected YAML structure in {path}: {type(document)!r}")
    return header, document


def _write_yaml(path: Path, header: str, document: dict) -> None:
    dump = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
    pieces: list[str] = []
    if header:
        pieces.append(header)
    if dump.strip():
        pieces.append(dump.rstrip())
    payload = "\n".join(pieces) + "\n"
    path.write_text(payload, encoding="utf-8")


def _normalize_modifiers(raw_modifiers: object) -> tuple[list[str], bool, set[str]]:
    if raw_modifiers is None:
        return [], False, set()
    if not isinstance(raw_modifiers, list):
        raise TypeError(f"Expected a list of modifiers, got {type(raw_modifiers)!r}")

    source_list = ["" if item is None else str(item).strip() for item in raw_modifiers]
    seen: dict[str, str] = {}
    duplicates: set[str] = set()
    for item in source_list:
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            duplicates.add(item)
            continue
        seen[key] = item

    normalized = [seen[key] for key in sorted(seen)]
    changed = normalized != raw_modifiers
    return normalized, changed, duplicates


def _prepare_rarity_entries(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise TypeError("Each rarity entry must be a mapping")
        rarity_name = item.get("name")
        if not rarity_name:
            raise ValueError("Each rarity entry must include a name")
        entry = dict(item)
        entry["name"] = rarity_name
        entry["modifiers"] = _coerce_modifier_list(entry.get("modifiers"))
        entries.append(entry)
    return entries


def _sort_rarity_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rarity_rank = {name: index for index, name in enumerate(_RARITY_ORDER)}

    def sort_key(entry: dict[str, Any]) -> tuple[float, str]:
        rarity_name = entry.get("name", "")
        rank = rarity_rank.get(rarity_name, float("inf"))
        return rank, rarity_name

    sorted_entries = sorted(entries, key=sort_key)
    return [dict(entry) for entry in sorted_entries]


def _coerce_modifier_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return ["" if item is None else str(item) for item in value]
    return [str(value)]


def get_modifier_info(
    modifier: str,
    rarity: str,
    modifiers_by_rarity: dict[str, list[ModifierWithSet]],
) -> Optional[ModifierWithSet]:
    """Look up a modifier's set information by name and rarity.

    Args:
        modifier: The modifier keyword to look up.
        rarity: The rarity level to search in.
        modifiers_by_rarity: The loaded modifiers dictionary.

    Returns:
        The ModifierWithSet if found, otherwise None.
    """
    modifiers_list = modifiers_by_rarity.get(rarity, [])
    for mod_with_set in modifiers_list:
        if mod_with_set.modifier == modifier:
            return mod_with_set
    return None
