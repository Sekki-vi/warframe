"""Ranking subagent — JSON-only tier lookup."""
from __future__ import annotations

import re
from typing import Any

from agents.knowledge.alias_index import load_alias_index
from agents.ranking.enrich import enrich_response
from agents.ranking.tier_store import lookup_tier, parse_tier_filter, slugs_for_tier
from wfi_lookup import slugify

_ITEM_QUERY = re.compile(
    r"\b(warframe|weapon|rifle|pistol|shotgun|melee|bow|archwing|companion|"
    r"sentinel|kavat|kubrow|mod|prime|what is|tell me about|describe|info on)\b",
    re.I,
)


def is_item_query(message: str) -> bool:
    """True when the message likely asks about a specific item or item class."""
    q = message.strip()
    if not q:
        return False
    if _ITEM_QUERY.search(q):
        return True
    if len(q.split()) <= 4:
        index = load_alias_index()
        for candidate in (q, q.lower()):
            if (
                candidate in index["name_to_doc"]
                or slugify(q) in index["slug_to_doc"]
                or slugify(q) in index["alias_to_doc"]
            ):
                return True
    return False


__all__ = [
    "enrich_response",
    "is_item_query",
    "lookup_tier",
    "parse_tier_filter",
    "slugs_for_tier",
]
