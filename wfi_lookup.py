"""Build warframe-items lookup tables (by uniqueName and slug)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests

from config import WFI_ALL_JSON, WFI_ALL_URL, WFI_LOOKUP_JSON


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower())
    return re.sub(r"_+", "_", s).strip("_")


def _pick_wfi_fields(item: dict[str, Any]) -> dict[str, Any]:
    """Extract plan-specified fields for RAG enrichment."""
    out: dict[str, Any] = {
        "name": item.get("name"),
        "uniqueName": item.get("uniqueName"),
        "category": item.get("category"),
        "type": item.get("type"),
        "description": item.get("description"),
        "masteryReq": item.get("masteryReq"),
        "imageName": item.get("imageName"),
        "rarity": item.get("rarity"),
        "polarity": item.get("polarity"),
        "fusionLimit": item.get("fusionLimit"),
        "levelStats": item.get("levelStats"),
        "isPrime": item.get("isPrime"),
    }
    if item.get("damage"):
        out["damage"] = item["damage"]
    for stat in ("criticalChance", "criticalMultiplier", "procChance", "fireRate", "totalDamage"):
        if stat in item:
            out[stat] = item[stat]
    if item.get("relicRewards"):
        rewards = [r.get("rewardName", "") for r in item["relicRewards"][:6]]
        out["relic_rewards_summary"] = "; ".join(rewards)
    if item.get("drops"):
        locs = sorted({d.get("location", "") for d in item["drops"] if d.get("location")})[:5]
        out["drop_locations"] = locs
    return {k: v for k, v in out.items() if v is not None}


def download_wfi_all(force: bool = False) -> Path:
    WFI_ALL_JSON.parent.mkdir(parents=True, exist_ok=True)
    if WFI_ALL_JSON.exists() and not force:
        return WFI_ALL_JSON
    print(f"Downloading {WFI_ALL_URL} ...")
    resp = requests.get(WFI_ALL_URL, timeout=120)
    resp.raise_for_status()
    WFI_ALL_JSON.write_bytes(resp.content)
    print(f"Saved {WFI_ALL_JSON}")
    return WFI_ALL_JSON


def build_lookup(all_items: list[dict[str, Any]]) -> dict[str, Any]:
    by_unique_name: dict[str, dict[str, Any]] = {}
    by_slug: dict[str, dict[str, Any]] = {}

    for item in all_items:
        fields = _pick_wfi_fields(item)
        unique = item.get("uniqueName")
        if unique:
            by_unique_name[unique] = fields
        name_slug = slugify(item.get("name", ""))
        if name_slug:
            by_slug[name_slug] = fields

        parent_name = item.get("name", "")
        parent_slug = slugify(parent_name)
        is_prime_parent = item.get("isPrime") or "Prime" in parent_name
        for comp in item.get("components") or []:
            comp_name = comp.get("name", "")
            if not comp_name:
                continue
            comp_fields = _pick_wfi_fields(comp)
            comp_fields["_parentName"] = parent_name
            comp_fields["_componentOf"] = parent_name
            comp_slug = slugify(comp_name)
            if is_prime_parent and parent_slug:
                key = f"{parent_slug}_{comp_slug}"
                by_slug[key] = comp_fields
                bp_key = f"{parent_slug}_{comp_slug}_blueprint"
                if comp_name == "Blueprint":
                    by_slug[bp_key] = comp_fields
            comp_unique = comp.get("uniqueName")
            if comp_unique:
                by_unique_name[comp_unique] = comp_fields

    return {"by_unique_name": by_unique_name, "by_slug": by_slug}


def load_or_build_lookup(force: bool = False) -> dict[str, Any]:
    if WFI_LOOKUP_JSON.exists() and not force:
        return json.loads(WFI_LOOKUP_JSON.read_text(encoding="utf-8"))

    download_wfi_all(force=force)
    all_items = json.loads(WFI_ALL_JSON.read_text(encoding="utf-8"))
    lookup = build_lookup(all_items)
    WFI_LOOKUP_JSON.parent.mkdir(parents=True, exist_ok=True)
    WFI_LOOKUP_JSON.write_text(json.dumps(lookup, ensure_ascii=False), encoding="utf-8")
    print(
        f"WFI lookup: {len(lookup['by_unique_name'])} uniqueName, "
        f"{len(lookup['by_slug'])} slug keys -> {WFI_LOOKUP_JSON}"
    )
    return lookup


def resolve_wfi(lookup: dict[str, Any], slug: str, game_ref: str | None) -> dict[str, Any] | None:
    if game_ref and game_ref in lookup["by_unique_name"]:
        return lookup["by_unique_name"][game_ref]
    if slug in lookup["by_slug"]:
        return lookup["by_slug"][slug]
    return None
