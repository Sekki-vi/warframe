"""Rank and sample taxonomy candidates by tier and stats."""
from __future__ import annotations

import random
import re
from typing import Any

from agents.knowledge.intent import QueryIntent
from agents.knowledge.tier_lists import lookup_tier, tier_rank

_STAT_DAMAGE = re.compile(r"(\d+(?:\.\d+)?)\s+total damage", re.I)
_STAT_CRIT = re.compile(r"(\d+)% crit", re.I)

_WARFRAME_PART_SUFFIXES = (
    "_blueprint",
    "_neuroptics",
    "_chassis",
    "_systems",
    "_harness",
    "_carapace",
    "_wings",
    "_cerebrum",
    "_neural",
)


def _stat_score(doc: dict[str, Any]) -> float:
    text = doc.get("metadata_text") or doc.get("text") or ""
    score = 0.0
    m = _STAT_DAMAGE.search(text)
    if m:
        score += float(m.group(1)) * 0.01
    m = _STAT_CRIT.search(text)
    if m:
        score += float(m.group(1))
    if doc.get("tradable"):
        score += 5.0
    return score


def _attach_tier(doc: dict[str, Any]) -> dict[str, Any]:
    ec = doc.get("equipment_class") or ""
    tier = doc.get("tier") or lookup_tier(doc.get("slug") or doc.get("id") or "", ec)
    return {**doc, "tier": tier}


def _filter_by_variant(docs: list[dict[str, Any]], variant: str | None) -> list[dict[str, Any]]:
    if not variant:
        return docs
    return [d for d in docs if (d.get("item_variant") or "base") == variant]


def rank_candidates(
    docs: list[dict[str, Any]],
    *,
    intent: QueryIntent,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Sort and sample docs for browse/recommend/random intents."""
    if not docs:
        return []

    enriched = [_attach_tier(d) for d in docs]

    if intent.want_mods:
        pool = enriched
    else:
        pool = [d for d in enriched if d.get("equipment_class") != "mods"]

    pool = _filter_by_variant(pool, intent.variant)

    if not pool:
        return []

    rng = random.Random(seed)

    if intent.tier_filter:
        tf = intent.tier_filter.upper()
        pool = [d for d in pool if (d.get("tier") or "").upper() == tf]
        if not pool:
            return []
        rng.shuffle(pool)
        return pool[: intent.result_count]

    if intent.kind == "random":
        return [rng.choice(pool)]

    if intent.speed_sort:
        pool.sort(key=lambda d: -(d.get("sprint_speed") or 0.0))
        return pool[: intent.result_count]

    pool.sort(
        key=lambda d: (
            tier_rank(d.get("tier")),
            -_stat_score(d),
            d.get("name") or "",
        )
    )

    if intent.kind == "recommend":
        best_rank = tier_rank(pool[0].get("tier"))
        top_bucket = [d for d in pool if tier_rank(d.get("tier")) == best_rank]
        rng.shuffle(top_bucket)
        rest = [d for d in pool if d not in top_bucket]
        ordered = top_bucket + rest
        return ordered[: intent.result_count]

    return pool[: intent.result_count]


def is_warframe_doc(doc: dict[str, Any]) -> bool:
    """True for full warframe entries, not blueprints or parts."""
    if doc.get("equipment_class") != "warframes":
        return False
    slug = doc.get("slug") or doc.get("id") or ""
    if any(slug.endswith(sfx) for sfx in _WARFRAME_PART_SUFFIXES):
        return False
    typ = (doc.get("type") or "").lower()
    if typ and typ not in ("warframe", "warframes"):
        return False
    return True
