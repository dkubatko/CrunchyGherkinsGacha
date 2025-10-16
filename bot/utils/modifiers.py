"""Helpers for loading modifier keyword lists from YAML season files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

LOGGER = logging.getLogger(__name__)

_MODIFIERS_DIR = Path(__file__).resolve().parents[1] / "data" / "modifiers"
_RARITY_ORDER = ("Common", "Rare", "Epic", "Legendary")


def load_modifiers(seasons: Optional[Iterable[str]] = None) -> dict[str, list[str]]:
    """Load modifier keywords grouped by rarity for the provided seasons."""
    ensure_logging_initialized()
    season_files = _discover_season_files(seasons)
    combined: dict[str, list[str]] = {}
    cross_rarity_tracker: dict[str, dict[str, str]] = {}

    for season_name, file_path in season_files:
        LOGGER.info("Loading modifiers from %s...", file_path.name)
        header, document = _read_yaml(file_path)
        if not isinstance(document, dict):
            raise ValueError(f"Expected mapping at top level in {file_path.name}")

        payload = document.get("rarities")
        if not isinstance(payload, list):
            raise ValueError(f"Expected 'rarities' to be a list of entries in {file_path.name}")

        rarity_entries = _prepare_rarity_entries(payload)
        mutated = False

        for entry in rarity_entries:
            rarity = entry.get("name")
            if not rarity:
                continue

            raw_modifiers = entry.get("modifiers", [])
            normalized, changed, duplicates = _normalize_modifiers(raw_modifiers)
            if duplicates:
                LOGGER.info(
                    "Dropped duplicate modifiers for season %s rarity %s: %s",
                    season_name,
                    rarity,
                    sorted(duplicates),
                )
            if changed:
                entry["modifiers"] = normalized
                mutated = True
            combined.setdefault(rarity, []).extend(normalized)

            for item in normalized:
                key = item.casefold()
                rarity_map = cross_rarity_tracker.setdefault(key, {})
                rarity_map[rarity] = item

        final_entries = _sort_rarity_entries(rarity_entries)
        if final_entries != payload:
            mutated = True

        if mutated:
            document["rarities"] = final_entries
            _write_yaml(file_path, header, document)

    aggregated: dict[str, list[str]] = {}
    for rarity, modifiers in combined.items():
        normalized, _, duplicates = _normalize_modifiers(modifiers)
        if duplicates:
            LOGGER.info(
                "Dropped duplicate modifiers across seasons for rarity %s: %s",
                rarity,
                sorted(duplicates),
            )
        aggregated[rarity] = normalized

    ordered: dict[str, list[str]] = {}
    for rarity in _RARITY_ORDER:
        ordered[rarity] = aggregated.pop(rarity, [])

    for rarity in sorted(aggregated):
        ordered[rarity] = aggregated[rarity]

    rarity_rank = {name: index for index, name in enumerate(_RARITY_ORDER)}

    for rarity_map in cross_rarity_tracker.values():
        if len(rarity_map) > 1:
            sample_value = next(iter(rarity_map.values()))
            rarities_list = ", ".join(
                sorted(rarity_map, key=lambda rarity: rarity_rank.get(rarity, float("inf")))
            )
            LOGGER.warning(
                "Modifier '%s' appears in multiple rarities: %s",
                sample_value,
                rarities_list,
            )

    return ordered


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


def _discover_season_files(seasons: Optional[Iterable[str]]) -> list[tuple[str, Path]]:
    if not _MODIFIERS_DIR.is_dir():
        raise FileNotFoundError(f"Modifiers directory not found at {_MODIFIERS_DIR}")
    if seasons is None:
        files = sorted(_MODIFIERS_DIR.glob("*.yaml"))
        return [(path.stem, path) for path in files]

    if isinstance(seasons, str):
        season_names = [seasons]
    else:
        season_names = list(dict.fromkeys(seasons))

    result: list[tuple[str, Path]] = []
    for name in season_names:
        path = _MODIFIERS_DIR / f"{name}.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"Unknown modifiers season '{name}' at {path}")
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
