"""Merge order aggregates with WFM + WFI into RAG-ready documents."""
from __future__ import annotations

import json
from math import isnan
from typing import Any

from config import RAG_DOCS_JSON, RAG_DOCS_JSONL, WFI_CDN_BASE
from wfi_lookup import resolve_wfi


def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    if isinstance(val, float) and isnan(val):
        return None
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def _doc_id(slug: str, rank: int | None, subtype: str | None) -> str:
    return f"{slug}|rank:{rank if rank is not None else ''}|subtype:{subtype or ''}"


def _rank_effect(wfi: dict[str, Any] | None, rank: int | None) -> str | None:
    if not wfi or rank is None:
        return None
    rank_idx = int(rank)
    stats = wfi.get("levelStats")
    if not stats or rank_idx >= len(stats):
        return None
    level = stats[rank_idx]
    parts = level.get("stats") if isinstance(level, dict) else None
    if parts:
        return "; ".join(parts)
    return None


def _weapon_stats_summary(wfi: dict[str, Any] | None) -> str | None:
    if not wfi:
        return None
    dmg = wfi.get("damage") or {}
    total = dmg.get("total") or wfi.get("totalDamage")
    if not total:
        return None
    crit = wfi.get("criticalChance")
    status = wfi.get("procChance")
    rate = wfi.get("fireRate")
    parts = [f"{total} total damage"]
    if crit is not None:
        parts.append(f"{round(crit * 100)}% crit")
    if status is not None:
        parts.append(f"{round(status * 100)}% status")
    if rate is not None:
        parts.append(f"{rate} fire rate")
    return ", ".join(parts)


def _format_side(label: str, stats: dict[str, Any] | None) -> str:
    if not stats or stats.get("count", 0) == 0:
        return f"No {label} orders."
    return (
        f"{stats['count']} {label} orders "
        f"(median {stats['platinum_median']:.0f}p, "
        f"range {stats['platinum_min']:.0f}–{stats['platinum_max']:.0f}p)"
    )


def build_embedding_text(
    agg: dict[str, Any],
    wfm: dict[str, Any] | None,
    wfi: dict[str, Any] | None,
    set_info: dict[str, Any] | None,
) -> str:
    name = (wfm or {}).get("name") or agg.get("item_name") or agg["slug"]
    slug = agg["slug"]
    rank = _safe_int(agg.get("rank"))
    subtype = agg.get("subtype")
    if isinstance(subtype, float) and isnan(subtype):
        subtype = None
    elif subtype is not None:
        subtype = str(subtype).strip() or None

    lines: list[str] = []
    label = name
    if subtype:
        label = f"{subtype} {name}"
    if rank is not None:
        label = f"{label} (rank {rank})"
    lines.append(f"{label} ({slug}).")

    desc = (wfm or {}).get("description") or (wfi or {}).get("description")
    if desc:
        lines.append(f"Description: {desc}")

    if wfi:
        cat = wfi.get("category")
        typ = wfi.get("type")
        mr = wfi.get("masteryReq") or (wfm or {}).get("reqMasteryRank")
        if cat or typ:
            bits = [b for b in (cat, typ) if b]
            lines.append(f"Category: {' / '.join(bits)}.")
        if mr is not None:
            lines.append(f"Mastery rank required: {mr}.")
        if wfi.get("vaulted"):
            lines.append("Status: vaulted.")
        if wfi.get("rarity"):
            lines.append(f"Rarity: {wfi['rarity']}.")
        if wfi.get("polarity"):
            lines.append(f"Polarity: {wfi['polarity']}.")
        rank_fx = _rank_effect(wfi, rank)
        if rank_fx:
            lines.append(f"Rank {rank} effect: {rank_fx}.")
        stats = _weapon_stats_summary(wfi)
        if stats:
            lines.append(f"Stats: {stats}.")
        if wfi.get("relic_rewards_summary"):
            lines.append(f"Relic rewards include: {wfi['relic_rewards_summary']}.")
        if wfi.get("drop_locations"):
            lines.append(f"Drop locations: {', '.join(wfi['drop_locations'])}.")

    if wfm:
        if wfm.get("tradingTax") is not None:
            lines.append(f"Trading tax: {wfm['tradingTax']} credits.")
        if wfm.get("ducats") is not None:
            lines.append(f"Ducats: {wfm['ducats']}.")
        if wfm.get("tags"):
            lines.append(f"Tags: {', '.join(wfm['tags'])}.")

    if set_info and set_info.get("set_parts_slugs"):
        parts = ", ".join(set_info["set_parts_slugs"])
        lines.append(f"Set includes: {parts}.")

    snap = agg.get("price_snapshot_date", "unknown")
    lines.append(f"Market prices as of {snap}:")
    lines.append(_format_side("sell", agg.get("sell")))
    lines.append(_format_side("buy", agg.get("buy")))

    return " ".join(lines)


def merge_documents(
    aggregates: list[dict[str, Any]],
    wfm_by_slug: dict[str, dict[str, Any]],
    wfi_lookup: dict[str, Any],
    prime_sets: dict[str, Any],
) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []

    for agg in aggregates:
        slug = agg["slug"]
        rank_raw = agg.get("rank")
        rank = _safe_int(rank_raw)
        subtype = agg.get("subtype")
        wfm = wfm_by_slug.get(slug)
        game_ref = (wfm or {}).get("gameRef")
        wfi = resolve_wfi(wfi_lookup, slug, game_ref)

        set_info = prime_sets.get(slug) if slug.endswith("_prime_set") else None

        wfi_out = None
        if wfi:
            wfi_out = dict(wfi)
            if wfi_out.get("imageName"):
                wfi_out["image_url"] = WFI_CDN_BASE + wfi_out["imageName"]
            rank_fx = _rank_effect(wfi, rank)
            if rank_fx:
                wfi_out["rank_effect"] = rank_fx
            stats = _weapon_stats_summary(wfi)
            if stats:
                wfi_out["stats_summary"] = stats
            wfi_out.pop("levelStats", None)

        wfm_out = None
        if wfm:
            wfm_out = {k: wfm[k] for k in (
                "id", "slug", "gameRef", "tags", "reqMasteryRank", "tradingTax",
                "ducats", "tradable", "setRoot", "name", "description", "wikiLink",
                "image_url", "thumb_url",
            ) if k in wfm}
            if set_info:
                wfm_out["set_parts_slugs"] = set_info.get("set_parts_slugs", [])

        image_url = (wfm or {}).get("image_url") or (wfi_out or {}).get("image_url")

        doc = {
            "id": _doc_id(slug, rank, subtype),
            "slug": slug,
            "rank": rank,
            "subtype": subtype,
            "market": {
                "item_name": agg.get("item_name"),
                "is_prime_part": agg.get("is_prime_part"),
                "price_snapshot_date": agg.get("price_snapshot_date"),
                "sell": agg.get("sell"),
                "buy": agg.get("buy"),
            },
            "wfm": wfm_out,
            "wfi": wfi_out,
            "image_url": image_url,
            "text_for_embedding": build_embedding_text(agg, wfm, wfi, set_info),
        }
        docs.append(doc)

    return docs


def _json_clean(obj: Any) -> Any:
    if isinstance(obj, float) and isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: _json_clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_clean(v) for v in obj]
    return obj


def save_documents(docs: list[dict[str, Any]]) -> None:
    docs = [_json_clean(d) for d in docs]
    RAG_DOCS_JSON.parent.mkdir(parents=True, exist_ok=True)
    RAG_DOCS_JSON.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")
    with RAG_DOCS_JSONL.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
    print(f"Saved {len(docs)} RAG documents:")
    print(f"  {RAG_DOCS_JSON}")
    print(f"  {RAG_DOCS_JSONL}")
