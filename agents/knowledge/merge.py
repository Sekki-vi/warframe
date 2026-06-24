"""Merge and rerank retrieval hits from multiple sources."""
from __future__ import annotations

from typing import Any

from agents.knowledge.tradable_registry import EXCLUDED_EQUIPMENT

SEMANTIC_MIN_SCORE = 0.35


def _is_noise_hit(hit: dict[str, Any]) -> bool:
    ec = hit.get("equipment_class") or ""
    slug = hit.get("slug") or hit.get("doc_id") or ""
    if ec in EXCLUDED_EQUIPMENT:
        return True
    if slug.endswith("_skin"):
        return True
    return False


def merge_hits(
    *hit_lists: list[dict[str, Any]],
    max_results: int = 5,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    priority = {"exact": 3, "taxonomy": 2, "keyword": 2, "semantic": 1}

    for hits in hit_lists:
        for hit in hits:
            doc_id = hit.get("doc_id") or hit.get("slug") or ""
            if not doc_id:
                continue
            src = hit.get("source", "semantic")
            score = float(hit.get("score") or 0)

            if src == "semantic":
                if score < SEMANTIC_MIN_SCORE or _is_noise_hit(hit):
                    continue

            boost = priority.get(src, 0) * 10 + score
            existing = merged.get(doc_id)
            if existing is None or boost > existing["_boost"]:
                merged[doc_id] = {**hit, "_boost": boost}

    ranked = sorted(merged.values(), key=lambda h: h["_boost"], reverse=True)

    exact_hits = [h for h in ranked if h.get("source") == "exact"]
    if exact_hits:
        clean = {k: v for k, v in exact_hits[0].items() if k != "_boost"}
        return [clean]

    out: list[dict[str, Any]] = []
    for hit in ranked[:max_results]:
        clean = {k: v for k, v in hit.items() if k != "_boost"}
        out.append(clean)
    return out
