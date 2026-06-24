"""Keyword, exact, and taxonomy retrieval."""
from __future__ import annotations

from typing import Any

from agents.knowledge.alias_index import load_alias_index
from agents.knowledge.intent import QueryIntent, _detect_mods_query, _detect_subtypes, strip_question_prefix
from agents.knowledge.rank import is_warframe_doc, rank_candidates
from agents.knowledge.tier_lists import lookup_tier
from agents.knowledge.wiki import component_display_name, compute_wiki_url
from wfi_lookup import slugify


def _doc_to_hit(doc: dict[str, Any], source: str, score: float = 1.0) -> dict[str, Any]:
    slug = doc.get("slug") or doc.get("id") or ""
    ec = doc.get("equipment_class") or ""
    name = component_display_name(slug, doc.get("name") or "", ec)
    wiki = compute_wiki_url(name, doc.get("item_variant") or "", ec)
    return {
        "doc_id": slug or doc.get("id") or "",
        "name": name,
        "slug": slug,
        "category": doc.get("category") or "",
        "type": doc.get("type") or "",
        "equipment_class": ec,
        "weapon_subtype": doc.get("weapon_subtype") or "",
        "taxonomy": doc.get("taxonomy") or "",
        "tier": doc.get("tier") or "",
        "item_variant": doc.get("item_variant") or "",
        "image_url": doc.get("image_url") or "",
        "wiki_link": wiki,
        "description": doc.get("description") or "",
        "text": doc.get("metadata_text") or doc.get("text") or "",
        "score": score,
        "source": source,
    }


def _normalize_query(query: str) -> str:
    q = query.strip().lower()
    if q.endswith(" set"):
        q = q[:-4].strip()
    return q


def _exact_match_candidates(query: str) -> list[str]:
    raw = _normalize_query(query)
    stripped = _normalize_query(strip_question_prefix(query))
    return list(
        dict.fromkeys(
            [
                raw,
                stripped,
                slugify(query),
                slugify(strip_question_prefix(query)),
                slugify(raw),
                slugify(stripped),
            ]
        )
    )


def exact_match(query: str, index: dict[str, Any] | None = None) -> dict[str, Any] | None:
    index = index or load_alias_index()
    docs_by_id = index["docs_by_id"]

    for q in _exact_match_candidates(query):
        if not q:
            continue
        doc_id = (
            index["name_to_doc"].get(q)
            or index["slug_to_doc"].get(q)
            or index["alias_to_doc"].get(q)
        )
        if doc_id and doc_id in docs_by_id:
            return _doc_to_hit(docs_by_id[doc_id], "exact", 1.0)
    return None


def _filter_pool(pool: list[dict[str, Any]], intent: QueryIntent) -> list[dict[str, Any]]:
    if intent.variant:
        pool = [d for d in pool if (d.get("item_variant") or "base") == intent.variant]
    if intent.tier_filter:
        tf = intent.tier_filter.upper()
        pool = [
            d
            for d in pool
            if (d.get("tier") or lookup_tier(d.get("slug") or "", d.get("equipment_class") or "")).upper()
            == tf
        ]
    return pool


def _collect_warframe_pool(index: dict[str, Any], intent: QueryIntent) -> list[dict[str, Any]]:
    docs_by_id = index["docs_by_id"]
    pool: list[dict[str, Any]] = []
    for doc_id in index.get("equipment_class_to_docs", {}).get("warframes", []):
        doc = docs_by_id.get(doc_id)
        if doc and is_warframe_doc(doc):
            pool.append(doc)
    return _filter_pool(pool, intent)


def _collect_variant_weapon_pool(index: dict[str, Any], intent: QueryIntent) -> list[dict[str, Any]]:
    if not intent.variant:
        return []
    docs_by_id = index["docs_by_id"]
    pool: list[dict[str, Any]] = []
    for doc_id in index.get("variant_to_docs", {}).get(intent.variant, []):
        doc = docs_by_id.get(doc_id)
        if not doc:
            continue
        ec = doc.get("equipment_class") or ""
        if ec in ("primary", "secondary", "melee", "archgun", "archmelee"):
            pool.append(doc)
    return _filter_pool(pool, intent)


def _collect_taxonomy_pool(
    query: str,
    index: dict[str, Any],
    intent: QueryIntent,
    *,
    subtypes: list[str] | None = None,
) -> list[dict[str, Any]]:
    if intent.browse_equipment_class == "warframes" and not intent.want_mods:
        return _collect_warframe_pool(index, intent)

    if intent.variant and not intent.subtypes and not intent.want_mods:
        pool = _collect_variant_weapon_pool(index, intent)
        if pool:
            return pool

    docs_by_id = index["docs_by_id"]
    subtypes = subtypes or intent.subtypes or _detect_subtypes(query)
    if not subtypes:
        return []

    want_mods = intent.want_mods or _detect_mods_query(query)
    pool: list[dict[str, Any]] = []
    seen: set[str] = set()

    for subtype in subtypes:
        if want_mods:
            doc_ids = index["weapon_subtype_to_docs"].get(f"{subtype}_mod", [])
            if not doc_ids:
                doc_ids = [
                    d
                    for d, doc in docs_by_id.items()
                    if doc.get("weapon_subtype") == f"{subtype}_mod"
                ]
        else:
            doc_ids = []
            for ec in ("primary", "secondary", "melee", "archgun", "archmelee"):
                tax_key = f"{ec}/{subtype}"
                doc_ids.extend(index["taxonomy_to_docs"].get(tax_key, []))
            doc_ids = list(dict.fromkeys(doc_ids))

        for doc_id in doc_ids:
            if doc_id in seen:
                continue
            doc = docs_by_id.get(doc_id)
            if not doc:
                continue
            if not want_mods and doc.get("equipment_class") == "mods":
                continue
            seen.add(doc_id)
            pool.append(doc)

    return _filter_pool(pool, intent)


def taxonomy_search(
    query: str,
    intent: QueryIntent,
    index: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    index = index or load_alias_index()
    pool = _collect_taxonomy_pool(query, index, intent)
    if not pool:
        return []

    ranked = rank_candidates(pool, intent=intent, seed=hash(query) & 0xFFFFFFFF)
    return [_doc_to_hit(doc, "taxonomy", 0.95 - i * 0.01) for i, doc in enumerate(ranked)]


def _mod_context_filter(query: str, doc: dict[str, Any]) -> bool:
    q = query.lower()
    tax = doc.get("taxonomy") or ""
    ws = doc.get("weapon_subtype") or ""

    if "melee" in q:
        return "melee" in tax or ws.endswith("melee_mod")
    if "shotgun" in q and "mod" in q:
        return "shotgun" in tax
    if "rifle" in q and "mod" in q:
        return "rifle" in tax
    if "pistol" in q and "mod" in q:
        return "pistol" in tax or "dual_pistols" in tax
    if "warframe" in q and "mod" in q:
        return tax == "mods/warframe_mod"
    return True


def _effect_search(
    query: str,
    index: dict[str, Any],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if "mod" not in query.lower():
        return []

    q = query.lower()
    effect_index = index.get("effect_to_docs") or {}
    docs_by_id = index["docs_by_id"]

    phrases = sorted(effect_index.keys(), key=len, reverse=True)
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()

    for phrase in phrases:
        if phrase in q:
            for doc_id in effect_index[phrase]:
                if doc_id in seen:
                    continue
                doc = docs_by_id.get(doc_id)
                if not doc or doc.get("equipment_class") != "mods":
                    continue
                if not _mod_context_filter(query, doc):
                    continue
                seen.add(doc_id)
                score = 0.98 if doc.get("slug", "").startswith("primed_") else 0.92
                hits.append(_doc_to_hit(doc, "keyword", score))

    if not hits:
        return []

    hits.sort(
        key=lambda h: (
            0 if (h.get("slug") or "").startswith("primed_") else 1,
            -(h.get("score") or 0),
        )
    )
    return hits[:limit]


def keyword_search(
    query: str,
    intent: QueryIntent,
    index: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    index = index or load_alias_index()
    exact = exact_match(query, index)
    if exact:
        return [exact]

    if intent.kind == "single":
        return []

    has_browse = intent.subtypes or intent.browse_equipment_class or (
        intent.variant and not intent.want_mods
    )

    if has_browse and (intent.kind in ("random", "recommend") or _detect_mods_query(query)):
        tax_hits = taxonomy_search(query, intent, index)
        if tax_hits:
            return tax_hits

    if has_browse and intent.kind == "lookup":
        pool = _collect_taxonomy_pool(query, index, intent)
        if pool and not _detect_mods_query(query):
            browse_intent = QueryIntent(
                kind="recommend",
                result_count=intent.result_count,
                subtypes=intent.subtypes,
                want_mods=intent.want_mods,
                variant=intent.variant,
                browse_equipment_class=intent.browse_equipment_class,
                tier_filter=intent.tier_filter,
            )
            ranked = rank_candidates(pool, intent=browse_intent, seed=hash(query) & 0xFFFFFFFF)
            return [_doc_to_hit(d, "taxonomy", 0.9) for d in ranked[: intent.result_count]]

    effect_hits = _effect_search(query, index, limit=intent.result_count)
    if effect_hits:
        return effect_hits

    return []
