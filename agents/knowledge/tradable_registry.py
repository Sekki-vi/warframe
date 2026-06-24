"""Warframe Market tradable item registry (CSV baseline + live API)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import CACHE_DIR, ITEMS_CSV
from wfm_catalog import fetch_items_manifest

TRADABLE_SLUGS_JSON = CACHE_DIR / "tradable_slugs.json"

EXCLUDED_EQUIPMENT = frozenset({"skins", "glyphs", "sigils", "node", "misc"})


def _load_csv_slugs() -> set[str]:
    if not ITEMS_CSV.exists():
        return set()
    import csv

    slugs: set[str] = set()
    with ITEMS_CSV.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            slug = (row.get("slug") or "").strip()
            if slug:
                slugs.add(slug)
    return slugs


def _load_api_tradable(wfm_by_slug: dict[str, dict[str, Any]]) -> set[str]:
    slugs: set[str] = set()
    for slug, item in wfm_by_slug.items():
        if item.get("tradable") is True:
            slugs.add(slug)
    return slugs


def build_tradable_registry(
    wfm_by_slug: dict[str, dict[str, Any]] | None = None,
    *,
    force_wfm: bool = False,
) -> dict[str, Any]:
    """WFM manifest items where tradable is True (API-only for inclusion)."""
    if wfm_by_slug is None:
        wfm_by_slug = fetch_items_manifest(force=force_wfm)

    csv_slugs = _load_csv_slugs()
    api_slugs = _load_api_tradable(wfm_by_slug)
    merged = api_slugs

    delta = sorted(api_slugs - csv_slugs)
    registry = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "csv_count": len(csv_slugs),
        "api_count": len(api_slugs),
        "merged_count": len(merged),
        "delta_from_csv": delta[:50],
        "delta_total": len(delta),
        "slugs": sorted(merged),
    }
    TRADABLE_SLUGS_JSON.parent.mkdir(parents=True, exist_ok=True)
    TRADABLE_SLUGS_JSON.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Tradable registry: csv={len(csv_slugs)} api={len(api_slugs)} "
        f"merged={len(merged)} new_since_csv={len(delta)}"
    )
    return registry


def load_tradable_slugs(*, force_wfm: bool = False) -> set[str]:
    if TRADABLE_SLUGS_JSON.exists() and not force_wfm:
        data = json.loads(TRADABLE_SLUGS_JSON.read_text(encoding="utf-8"))
        return set(data.get("slugs") or [])
    return set(build_tradable_registry(force_wfm=force_wfm)["slugs"])


def wfm_slug_candidates(wfi_slug: str) -> list[str]:
    """Fallback slugs for built weapons / sets on market."""
    return [wfi_slug, f"{wfi_slug}_set", f"{wfi_slug}_blueprint"]


def resolve_tradable_wfm_slug(
    wfi_slug: str,
    wfi: dict[str, Any],
    tradable_slugs: set[str],
    name_to_wfm: dict[str, str],
    wfi_to_wfm: dict[str, str],
) -> str | None:
    """Return WFM slug that is in tradable set, trying direct + fallbacks."""
    from wfi_lookup import slugify

    candidates: list[str] = []
    if wfi_slug in wfi_to_wfm:
        candidates.append(wfi_to_wfm[wfi_slug])
    name = wfi.get("name") or ""
    if name:
        key = slugify(name)
        if key in name_to_wfm:
            candidates.append(name_to_wfm[key])
    candidates.extend(wfm_slug_candidates(wfi_slug))
    seen: set[str] = set()
    for slug in candidates:
        if slug and slug not in seen:
            seen.add(slug)
            if slug in tradable_slugs:
                return slug
    return None


def should_include_wfi_doc(
    slug: str,
    wfi: dict[str, Any],
    *,
    equipment_class: str,
    item_variant: str,
    tradable_slugs: set[str],
    wfm_by_slug: dict[str, dict[str, Any]],
    name_to_wfm: dict[str, str],
    wfi_to_wfm: dict[str, str],
) -> tuple[bool, str]:
    """Return (include, exclusion_reason)."""
    if equipment_class in EXCLUDED_EQUIPMENT:
        return False, "category"
    if slug.endswith("_skin"):
        return False, "category"

    if equipment_class == "warframes":
        is_prime = item_variant == "prime" or slug.endswith("_prime_set")
        is_prime_part = "_prime_" in slug and any(
            slug.endswith(s) for s in ("_blueprint", "_neuroptics", "_chassis", "_systems")
        )
        if not (is_prime or is_prime_part):
            return False, "non_prime_warframe"

    wfm_slug = resolve_tradable_wfm_slug(
        slug, wfi, tradable_slugs, name_to_wfm, wfi_to_wfm
    )
    if not wfm_slug:
        return False, "not_on_market"
    wfm_item = wfm_by_slug.get(wfm_slug) or {}
    if wfm_item.get("tradable") is not True:
        return False, "not_on_market"
    return True, ""
