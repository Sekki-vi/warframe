"""Aggregate order CSV by slug + rank + subtype."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from config import AGGREGATES_JSON, ORDERS_CSV


def _normalize_rank(val: Any) -> int | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _normalize_subtype(val: Any) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s or None


def _price_stats(group: pd.DataFrame) -> dict[str, Any]:
    platinum = group["platinum"].astype(float)
    quantity = group["quantity"].astype(float)
    return {
        "count": int(len(group)),
        "platinum_min": float(platinum.min()),
        "platinum_max": float(platinum.max()),
        "platinum_median": float(platinum.median()),
        "platinum_p25": float(platinum.quantile(0.25)),
        "platinum_p75": float(platinum.quantile(0.75)),
        "total_quantity": int(quantity.sum()),
        "avg_quantity": round(float(quantity.mean()), 2),
    }


def aggregate_orders(force: bool = False) -> list[dict[str, Any]]:
    if AGGREGATES_JSON.exists() and not force:
        return json.loads(AGGREGATES_JSON.read_text(encoding="utf-8"))

    print(f"Loading orders from {ORDERS_CSV} ...")
    df = pd.read_csv(ORDERS_CSV, low_memory=False)
    df["rank_norm"] = df["rank"].apply(_normalize_rank)
    df["subtype_norm"] = df["subtype"].apply(_normalize_subtype)
    df["is_prime_part"] = df["is_prime_part"].astype(str).str.lower() == "true"

    snapshot = str(df["pulled_at"].iloc[0])[:10] if len(df) else None

    group_cols = ["slug", "item_name", "is_prime_part", "rank_norm", "subtype_norm", "order_type"]
    results: list[dict[str, Any]] = []
    grouped = df.groupby(group_cols, dropna=False)

    # Pivot buy/sell per (slug, rank, subtype)
    keys: dict[tuple, dict[str, Any]] = {}
    for key, grp in grouped:
        slug, item_name, is_prime, rank, subtype, order_type = key
        rank = _normalize_rank(rank)
        subtype = _normalize_subtype(subtype)
        doc_key = (slug, rank, subtype)
        if doc_key not in keys:
            keys[doc_key] = {
                "slug": slug,
                "item_name": item_name,
                "is_prime_part": bool(is_prime),
                "rank": rank,
                "subtype": subtype,
                "price_snapshot_date": snapshot,
            }
        keys[doc_key][order_type] = _price_stats(grp)

    results = list(keys.values())
    AGGREGATES_JSON.parent.mkdir(parents=True, exist_ok=True)
    AGGREGATES_JSON.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    print(f"Aggregated {len(results)} groups -> {AGGREGATES_JSON}")
    return results
