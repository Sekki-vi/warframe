"""Semantic retrieval via Pinecone."""
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


def _match_to_hit(match: Any) -> dict[str, Any]:
    meta = match.metadata or {}
    return {
        "doc_id": meta.get("doc_id") or "",
        "name": meta.get("name") or "",
        "slug": meta.get("slug") or "",
        "category": meta.get("category") or "",
        "type": meta.get("type") or "",
        "equipment_class": meta.get("equipment_class") or "",
        "weapon_subtype": meta.get("weapon_subtype") or "",
        "taxonomy": meta.get("taxonomy") or "",
        "image_url": meta.get("image_url") or "",
        "wiki_link": meta.get("wiki_link") or "",
        "tier": meta.get("tier") or "",
        "item_variant": meta.get("item_variant") or "",
        "wfm_slug": meta.get("wfm_slug") or "",
        "description": meta.get("description") or "",
        "text": meta.get("text") or "",
        "score": float(match.score) if match.score is not None else 0.0,
        "source": "semantic",
    }


def semantic_search(query: str, *, top_k: int | None = None) -> list[dict[str, Any]]:
    cfg, client, index = _clients()
    k = top_k if top_k is not None else cfg["top_k"]
    embedding = client.embeddings.create(model=cfg["embed_model"], input=[query]).data[0].embedding
    results = index.query(
        namespace=cfg["namespace"],
        vector=embedding,
        top_k=k,
        include_metadata=True,
    )
    return [_match_to_hit(m) for m in results.matches]
