"""Resolve WFM set slugs and fetch market-listed build components."""
from __future__ import annotations

from typing import Any

from agents.market import client as wfm_client
from agents.market.live import CacheDict, get_item_live
from agents.knowledge.part_images import part_image_url

_SET_SUFFIX = "_set"


def resolve_set_slug(item_slug: str, wfm_slug: str | None = None) -> str | None:
    """Map a built item or WFM slug to the market set slug."""
    candidates: list[str] = []
    if wfm_slug:
        if wfm_slug.endswith(_SET_SUFFIX):
            return wfm_slug
        candidates.append(f"{wfm_slug}{_SET_SUFFIX}")
        candidates.append(wfm_slug)
    if item_slug:
        if item_slug.endswith(_SET_SUFFIX):
            return item_slug
        candidates.append(f"{item_slug}{_SET_SUFFIX}")
        candidates.append(item_slug)

    seen: set[str] = set()
    for slug in candidates:
        if slug and slug not in seen:
            seen.add(slug)
            item = wfm_client.get_item(slug)
            if item and (item.get("setRoot") or slug.endswith(_SET_SUFFIX)):
                return slug
    return None


def get_market_parts(
    set_slug: str,
    cache: CacheDict | None = None,
) -> list[dict[str, Any]]:
    """Return tradable components from GET /item/{set_slug}/set."""
    items = wfm_client.get_set_items(set_slug)
    parts: list[dict[str, Any]] = []
    for item in items:
        slug = item.get("slug") or ""
        if not slug or slug == set_slug:
            continue
        if item.get("setRoot"):
            continue
        if item.get("tradable") is not True:
            continue
        parts.append(
            {
                "slug": slug,
                "name": item.get("name") or slug.replace("_", " ").title(),
                "ducats": item.get("ducats"),
                "wfm_slug": slug,
                "image_url": part_image_url(slug) or item.get("image_url") or item.get("thumb_url") or "",
                "source": "wfm_set",
            }
        )
    return parts


def get_set_parts(
    item_slug: str,
    wfm_slug: str | None = None,
    *,
    cache: CacheDict | None = None,
) -> list[dict[str, Any]]:
    """Resolve set slug and return market-listed tradable parts."""
    set_slug = resolve_set_slug(item_slug, wfm_slug)
    if not set_slug:
        return []

    root = get_item_live(set_slug, cache)
    if root and root.get("tradable") is not True and not root.get("setRoot"):
        return []

    return get_market_parts(set_slug, cache)
