"""Fetch and cache Warframe Market v2 item manifest."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

from config import (
    WFM_API_BASE,
    WFM_ASSET_BASE,
    WFM_HEADERS,
    WFM_ITEMS_JSON,
    WFM_SETS_JSON,
)

WFM_DETAILS_JSON = WFM_ITEMS_JSON.parent / "wfm_item_details.json"
REQUEST_DELAY = 0.34  # ~3 req/s rate limit


def asset_url(relative_path: str | None) -> str | None:
    if not relative_path:
        return None
    return WFM_ASSET_BASE + relative_path.lstrip("/")


def _get_json(path: str) -> dict[str, Any]:
    url = f"{WFM_API_BASE}{path}"
    resp = requests.get(url, headers=WFM_HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _normalize_item(raw: dict[str, Any]) -> dict[str, Any]:
    i18n_en = (raw.get("i18n") or {}).get("en") or {}
    return {
        "id": raw.get("id"),
        "slug": raw.get("slug"),
        "gameRef": raw.get("gameRef"),
        "tags": raw.get("tags") or [],
        "reqMasteryRank": raw.get("reqMasteryRank"),
        "tradingTax": raw.get("tradingTax"),
        "ducats": raw.get("ducats"),
        "tradable": raw.get("tradable"),
        "setRoot": raw.get("setRoot"),
        "setParts": raw.get("setParts"),
        "name": i18n_en.get("name"),
        "description": i18n_en.get("description"),
        "wikiLink": i18n_en.get("wikiLink"),
        "icon": i18n_en.get("icon"),
        "thumb": i18n_en.get("thumb"),
        "image_url": asset_url(i18n_en.get("icon")),
        "thumb_url": asset_url(i18n_en.get("thumb")),
    }


def fetch_items_manifest(force: bool = False) -> dict[str, dict[str, Any]]:
    """Bulk manifest: ids, slugs, icons (no descriptions)."""
    WFM_ITEMS_JSON.parent.mkdir(parents=True, exist_ok=True)
    if WFM_ITEMS_JSON.exists() and not force:
        data = json.loads(WFM_ITEMS_JSON.read_text(encoding="utf-8"))
        return data["by_slug"]

    print("Fetching WFM /v2/versions ...")
    versions = _get_json("/versions")
    items_hash = versions.get("data", {}).get("collections", {}).get("items")
    print(f"  items collection hash: {items_hash}")

    print("Fetching WFM /v2/items (bulk, short form) ...")
    payload = _get_json("/items")
    items = payload.get("data") or []
    by_slug: dict[str, dict[str, Any]] = {}
    for raw in items:
        norm = _normalize_item(raw)
        if norm.get("slug"):
            by_slug[norm["slug"]] = norm

    WFM_ITEMS_JSON.write_text(
        json.dumps({"items_hash": items_hash, "by_slug": by_slug}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Cached {len(by_slug)} WFM items (bulk) -> {WFM_ITEMS_JSON}")
    return by_slug


def enrich_item_details(
    slugs: set[str],
    by_slug: dict[str, dict[str, Any]],
    force: bool = False,
) -> dict[str, dict[str, Any]]:
    """Fetch /v2/item/{slug} for full descriptions and set metadata."""
    WFM_DETAILS_JSON.parent.mkdir(parents=True, exist_ok=True)
    cached: dict[str, dict[str, Any]] = {}
    if WFM_DETAILS_JSON.exists() and not force:
        cached = json.loads(WFM_DETAILS_JSON.read_text(encoding="utf-8"))

    needed = sorted(s for s in slugs if s not in cached or force)
    if needed:
        print(f"Enriching {len(needed)} items via /v2/item/{{slug}} ...")
        for i, slug in enumerate(needed, 1):
            try:
                payload = _get_json(f"/item/{slug}")
                cached[slug] = _normalize_item(payload.get("data") or {})
            except requests.HTTPError as exc:
                print(f"  WARN {slug}: {exc}")
                cached[slug] = by_slug.get(slug, {"slug": slug, "error": str(exc)})
            if i % 100 == 0:
                print(f"  ... {i}/{len(needed)}")
                WFM_DETAILS_JSON.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
            time.sleep(REQUEST_DELAY)
        WFM_DETAILS_JSON.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
        print(f"Cached item details -> {WFM_DETAILS_JSON}")

    merged = dict(by_slug)
    for slug in slugs:
        if slug in cached:
            merged[slug] = {**merged.get(slug, {}), **cached[slug]}
    return merged


def fetch_prime_sets(by_slug: dict[str, dict[str, Any]], force: bool = False) -> dict[str, Any]:
    WFM_SETS_JSON.parent.mkdir(parents=True, exist_ok=True)
    if WFM_SETS_JSON.exists() and not force:
        data = json.loads(WFM_SETS_JSON.read_text(encoding="utf-8"))
        if data:
            return data

    set_slugs = sorted(s for s in by_slug if s.endswith("_prime_set"))
    sets_data: dict[str, Any] = {}

    print(f"Fetching set details for {len(set_slugs)} prime sets ...")
    for i, slug in enumerate(set_slugs, 1):
        try:
            payload = _get_json(f"/item/{slug}/set")
            items = payload.get("data", {}).get("items") or []
            part_slugs = [
                it["slug"]
                for it in items
                if it.get("slug") and it.get("slug") != slug and not it.get("setRoot")
            ]
            sets_data[slug] = {
                "set_parts_slugs": part_slugs,
                "parts": [_normalize_item(it) for it in items if it.get("slug") != slug],
            }
        except requests.HTTPError as exc:
            print(f"  WARN set {slug}: {exc}")
            sets_data[slug] = {"set_parts_slugs": [], "parts": [], "error": str(exc)}
        if i % 50 == 0:
            print(f"  ... {i}/{len(set_slugs)}")
            WFM_SETS_JSON.write_text(json.dumps(sets_data, ensure_ascii=False), encoding="utf-8")
        time.sleep(REQUEST_DELAY)

    WFM_SETS_JSON.write_text(json.dumps(sets_data, ensure_ascii=False), encoding="utf-8")
    print(f"Cached prime set expansions -> {WFM_SETS_JSON}")
    return sets_data
