"""Attach tier labels to knowledge agent responses."""
from __future__ import annotations

from typing import Any

from agents.ranking.tier_store import lookup_tier


def enrich_response(result: dict[str, Any]) -> dict[str, Any]:
    """Add tier to source cards when the resolved slug has a tier entry."""
    slug = result.get("resolved_slug") or ""
    equipment_class = result.get("equipment_class") or ""
    if not slug or not equipment_class:
        return result

    tier = lookup_tier(slug, equipment_class)
    if not tier:
        return result

    sources = []
    for src in result.get("sources") or []:
        updated = dict(src)
        if not updated.get("tier"):
            updated["tier"] = tier
        sources.append(updated)

    out = dict(result)
    out["sources"] = sources
    out["tier"] = tier
    return out
