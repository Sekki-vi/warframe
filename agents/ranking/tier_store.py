"""Load Overframe tier list JSON with mtime-based cache reload."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from config import PROJECT_ROOT

TIER_LISTS_DIR = PROJECT_ROOT / "data" / "tier_lists"
OVERFRAME_JSON = TIER_LISTS_DIR / "overframe.json"

_EQUIPMENT_TO_CATEGORY = {
    "primary": "primary",
    "secondary": "secondary",
    "melee": "melee",
    "archgun": "primary",
    "archmelee": "melee",
    "warframes": "warframes",
    "archwing": "archwing",
    "sentinels": "companions",
    "pets": "companions",
}

TIER_RANK = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4, "": 5, None: 5}

_cache: dict[str, dict[str, Any]] | None = None
_mtime: float = 0.0


def _load_overframe() -> dict[str, dict[str, Any]]:
    global _cache, _mtime
    if not OVERFRAME_JSON.exists():
        return {}
    mtime = OVERFRAME_JSON.stat().st_mtime
    if _cache is not None and _mtime == mtime:
        return _cache
    data = json.loads(OVERFRAME_JSON.read_text(encoding="utf-8"))
    _cache = data.get("categories") or {}
    _mtime = mtime
    return _cache


def _get_list(equipment_class: str) -> dict[str, Any]:
    category = _EQUIPMENT_TO_CATEGORY.get(equipment_class)
    if not category:
        return {}
    return _load_overframe().get(category) or {}


def lookup_tier(slug: str, equipment_class: str) -> str:
    """Return tier letter S–D or empty string."""
    data = _get_list(equipment_class)
    entry = data.get(slug) or {}
    return (entry.get("tier") or "").upper()


def tier_rank(tier: str | None) -> int:
    return TIER_RANK.get((tier or "").upper() if tier else "", 5)


def slugs_for_tier(tier: str, equipment_class: str | None = None) -> list[str]:
    """Return slugs ranked at the given tier letter."""
    target = tier.upper()
    classes = [equipment_class] if equipment_class else list(_EQUIPMENT_TO_CATEGORY)
    out: list[str] = []
    seen: set[str] = set()
    for ec in classes:
        if not ec:
            continue
        data = _get_list(ec)
        for slug, entry in data.items():
            if (entry.get("tier") or "").upper() == target and slug not in seen:
                seen.add(slug)
                out.append(slug)
    return out


def parse_tier_filter(query: str) -> str | None:
    m = re.search(
        r"\b([SABCD])\s*(?:-?\s*tier|-?\s*rank)\b|\b(?:tier|rank)\s*([SABCD])\b",
        query,
        re.I,
    )
    if not m:
        return None
    for g in m.groups():
        if g:
            return g.upper()
    return None
