"""Pinecone retrieval for chat."""
from __future__ import annotations

from typing import Any

from openai import OpenAI
from pinecone import Pinecone

from chat.config import get_chat_config

_index = None
_openai = None
_cfg: dict | None = None


def _clients() -> tuple[dict, OpenAI, Any]:
    global _index, _openai, _cfg
    if _cfg is None:
        _cfg = get_chat_config()
        _openai = OpenAI(api_key=_cfg["openai_key"])
        pc = Pinecone(api_key=_cfg["pinecone_key"])
        _index = pc.Index(_cfg["index_name"])
    return _cfg, _openai, _index


def _normalize_rank(rank_val: Any) -> int | None:
    if rank_val is None:
        return None
    try:
        r = int(rank_val)
    except (TypeError, ValueError):
        return None
    return None if r < 0 else r


def _match_to_source(match: Any) -> dict[str, Any]:
    meta = match.metadata or {}
    rank = _normalize_rank(meta.get("rank"))
    subtype = meta.get("subtype") or None
    sell_median = meta.get("sell_median")
    buy_median = meta.get("buy_median")
    return {
        "item_name": meta.get("item_name") or "",
        "slug": meta.get("slug") or "",
        "rank": rank,
        "subtype": subtype,
        "sell_median": float(sell_median) if sell_median is not None else None,
        "buy_median": float(buy_median) if buy_median is not None else None,
        "price_snapshot_date": meta.get("price_snapshot_date") or "",
        "image_url": meta.get("image_url") or "",
        "wiki_link": meta.get("wiki_link") or "",
        "category": meta.get("category") or "",
        "text": meta.get("text") or "",
        "score": float(match.score) if match.score is not None else 0.0,
    }


def search(query: str, *, top_k: int | None = None) -> list[dict[str, Any]]:
    """Embed query and return top-k Pinecone matches as source dicts."""
    cfg, client, index = _clients()
    k = top_k if top_k is not None else cfg["top_k"]
    embedding = client.embeddings.create(model=cfg["embed_model"], input=[query]).data[0].embedding
    results = index.query(
        namespace=cfg["namespace"],
        vector=embedding,
        top_k=k,
        include_metadata=True,
    )
    return [_match_to_source(m) for m in results.matches]
