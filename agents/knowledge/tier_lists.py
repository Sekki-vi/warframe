"""Load Overframe tier list JSON with mtime-based cache reload."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import PROJECT_ROOT

TIER_LISTS_DIR = PROJECT_ROOT / "data" / "tier_lists"

_EQUIPMENT_TO_FILE = {
    "primary": "overframe_primary.json",
    "secondary": "overframe_secondary.json",
    "melee": "overframe_melee.json",
    "archgun": "overframe_primary.json",
    "archmelee": "overframe_melee.json",
    "warframes": "overframe_warframes.json",
}

TIER_RANK = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4, "": 5, None: 5}

_cache: dict[str, dict[str, Any]] = {}
_mtimes: dict[str, float] = {}


def _load_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _get_list(equipment_class: str) -> dict[str, Any]:
    fname = _EQUIPMENT_TO_FILE.get(equipment_class)
    if not fname:
        return {}
    path = TIER_LISTS_DIR / fname
    key = str(path)
    mtime = path.stat().st_mtime if path.exists() else 0.0
    if key not in _cache or _mtimes.get(key) != mtime:
        _cache[key] = _load_file(path)
        _mtimes[key] = mtime
    return _cache[key]


def lookup_tier(slug: str, equipment_class: str) -> str:
    """Return tier letter S–D or empty string."""
    data = _get_list(equipment_class)
    entry = data.get(slug) or {}
    return (entry.get("tier") or "").upper()


def tier_rank(tier: str | None) -> int:
    return TIER_RANK.get((tier or "").upper() if tier else "", 5)


def all_tier_files() -> list[Path]:
    return [TIER_LISTS_DIR / f for f in _EQUIPMENT_TO_FILE.values()]
