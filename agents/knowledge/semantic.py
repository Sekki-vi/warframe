"""Semantic retrieval via Pinecone."""
from __future__ import annotations

from typing import Any

from openai import OpenAI
from pinecone import Pinecone

from agents.knowledge.wiki import component_display_name, compute_wiki_url
from agent_config import get_agent_config

_index = None
_openai = None
_cfg: dict | None = None


def _clients() -> tuple[dict, OpenAI, Any]:
    global _index, _openai, _cfg
    if _cfg is None:
        _cfg = get_agent_config()
        _openai = OpenAI(api_key=_cfg["openai_key"])
        pc = Pinecone(api_key=_cfg["pinecone_key"])
        _index = pc.Index(_cfg["index_name"])
    return _cfg, _openai, _index


def _match_to_hit(match: Any) -> dict[str, Any]:
    meta = match.metadata or {}
    slug = meta.get("slug") or ""
    ec = meta.get("equipment_class") or ""
    name = component_display_name(slug, meta.get("name") or "", ec)
    wiki = compute_wiki_url(name, meta.get("item_variant") or "", ec)
    return {
        "doc_id": meta.get("doc_id") or "",
        "name": name,
        "slug": slug,
        "category": meta.get("category") or "",
        "type": meta.get("type") or "",
        "equipment_class": ec,
        "weapon_subtype": meta.get("weapon_subtype") or "",
        "taxonomy": meta.get("taxonomy") or "",
        "image_url": meta.get("image_url") or "",
        "wiki_link": wiki,
        "tier": meta.get("tier") or "",
        "item_variant": meta.get("item_variant") or "",
        "description": meta.get("description") or "",
        "text": meta.get("text") or "",
        "sprint_speed": float(meta["sprint_speed"]) if meta.get("sprint_speed") is not None else None,
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
