"""Live WFM item lookup with per-request deduplication."""
from __future__ import annotations

from typing import Any

from agents.market import client as wfm_client

CacheDict = dict[str, Any]


def _cache_key(slug: str) -> str:
    return slug.strip().lower()


def get_item_live(slug: str, cache: CacheDict | None = None) -> dict[str, Any] | None:
    """GET /v2/item/{slug} with optional request-scoped cache."""
    if not slug:
        return None
    key = _cache_key(slug)
    if cache is not None and key in cache:
        return cache[key]

    item = wfm_client.get_item(slug)
    if cache is not None:
        cache[key] = item
    return item


def is_listed_on_market(slug: str, cache: CacheDict | None = None) -> bool:
    """True when item exists on WFM and tradable is True."""
    item = get_item_live(slug, cache)
    if not item:
        return False
    return item.get("tradable") is True


def check_listed(slug: str, cache: CacheDict | None = None) -> bool:
    """Alias for is_listed_on_market."""
    return is_listed_on_market(slug, cache)
