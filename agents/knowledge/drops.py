"""Hybrid drop-source resolution: WFI locations first, wiki acquisition fallback."""
from __future__ import annotations

from typing import Any

from agents.knowledge.wiki_drops import fetch_acquisition
from wfi_lookup import load_or_build_lookup


def _wfi_drop_locations(slug: str) -> list[str]:
    if not slug:
        return []
    wfi = load_or_build_lookup()["by_slug"].get(slug) or {}
    return list(wfi.get("drop_locations") or [])


def resolve_drop_sources(
    *,
    slug: str,
    wiki_link: str = "",
    drop_locations: list[str] | None = None,
) -> list[str]:
    """Return drop/acquisition source lines for an item."""
    locations = list(drop_locations or []) or _wfi_drop_locations(slug)
    if locations:
        return locations[:8]

    if wiki_link:
        wiki_sources = fetch_acquisition(wiki_link)
        if wiki_sources:
            return wiki_sources

    return []


def enrich_hit_drops(hit: dict[str, Any]) -> dict[str, Any]:
    """Attach drop_sources to a retrieval hit."""
    slug = hit.get("slug") or hit.get("doc_id") or ""
    sources = resolve_drop_sources(
        slug=slug,
        wiki_link=hit.get("wiki_link") or "",
        drop_locations=hit.get("drop_locations"),
    )
    if not sources:
        return hit
    return {**hit, "drop_sources": sources}
