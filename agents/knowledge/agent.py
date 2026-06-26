"""Knowledge Agent — non-tradable WFI Ordis sub-agent."""
from __future__ import annotations

import re
from typing import Any

from openai import OpenAI

from agents.knowledge.drops import enrich_hit_drops
from agents.knowledge.intent import QueryIntent, parse_query_intent
from agents.knowledge.alias_index import load_alias_index
from agents.knowledge.keyword import exact_match, keyword_search
from agents.knowledge.merge import merge_hits
from agents.knowledge.semantic import semantic_search
from agents.knowledge.tradable_registry import load_tradable_slugs
from agent_config import get_agent_config
from wfi_lookup import load_or_build_lookup, slugify

SYSTEM_PROMPT = """You are Ordis, a Cephalon knowledge subsystem aboard a Tenno's Orbiter.

Persona:
- Formal, helpful, and slightly dramatic in a sci-fi manner.
- Address the user as "Operator" occasionally.

Rules:
- Answer ONLY using the provided knowledge context. If context is insufficient, say so clearly.
- Keep replies concise: 2–4 sentences unless the Operator asks for more detail.
- Give a direct description only. Do NOT end with a question, offer, or prompt (e.g. "Would you like to know more?", "Shall I explain further?", "What would you like to know next?").
- If drop or acquisition sources are in the context, include them briefly in one sentence. Do not invent drop locations.
- Never mention prices, platinum, sellers, orders, or warframe.market listings.
- If asked about prices or trading, explain that market data is handled by a separate subsystem.
- Never invent item stats or names not present in the context.
"""

_client: OpenAI | None = None
_cfg: dict | None = None
_tradable_cache: set[str] | None = None


def _get_client() -> tuple[dict, OpenAI]:
    global _client, _cfg
    if _cfg is None:
        _cfg = get_agent_config()
        _client = OpenAI(api_key=_cfg["openai_key"])
    return _cfg, _client


def _tradable_slugs() -> set[str]:
    global _tradable_cache
    if _tradable_cache is None:
        _tradable_cache = load_tradable_slugs()
    return _tradable_cache


def _trim_history(history: list[dict[str, str]], max_turns: int) -> list[dict[str, str]]:
    if len(history) <= max_turns * 2:
        return history
    return history[-(max_turns * 2) :]


def _build_context(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "No relevant items were retrieved from the knowledge base."
    hit = hits[0]
    parts = [f"{hit.get('name')}"]
    if hit.get("text"):
        parts.append(hit["text"])
    drops = hit.get("drop_sources") or []
    if drops:
        parts.append("Drop sources: " + "; ".join(drops[:4]))
    return "\n".join(parts)


def _is_price_query(query: str) -> bool:
    q = query.lower()
    return bool(
        re.search(
            r"\b(price|platinum|cost|how much|sell|buy|seller|trade|market|who is selling)\b",
            q,
        )
    )


def _resolve_query_slug(query: str) -> tuple[str, str]:
    """Best-effort slug + display name from alias index / WFI lookup."""
    index = load_alias_index()
    candidates = [query.strip(), query.strip().lower()]
    for cand in candidates:
        if not cand:
            continue
        doc_id = (
            index["name_to_doc"].get(cand)
            or index["slug_to_doc"].get(slugify(cand))
            or index["alias_to_doc"].get(slugify(cand))
        )
        if doc_id:
            doc = index["docs_by_id"].get(doc_id) or {}
            return doc_id, doc.get("name") or doc_id.replace("_", " ").title()

    lookup = load_or_build_lookup()
    key = slugify(query)
    wfi = lookup["by_slug"].get(key)
    if wfi:
        return key, wfi.get("name") or key.replace("_", " ").title()
    return "", ""


def _tradable_guard(slug: str, wfi_name: str = "") -> str | None:
    """Return a short rejection message when slug is on WFM tradable set."""
    if not slug:
        return None
    tradable = _tradable_slugs()
    if slug in tradable or f"{slug}_set" in tradable:
        label = wfi_name or slug.replace("_", " ").title()
        return (
            f"Operator, {label} is a tradable market item. "
            "This knowledge interface covers non-tradable items only; "
            "market pricing will be handled by a separate subsystem."
        )
    return None


def retrieve(query: str) -> tuple[list[dict[str, Any]], QueryIntent]:
    intent = parse_query_intent(query)
    keyword_hits = keyword_search(query, intent)
    if keyword_hits:
        return keyword_hits[:1], intent
    semantic_hits = semantic_search(query, top_k=1)
    hits = merge_hits(keyword_hits, semantic_hits, max_results=1)
    return hits[:1], intent


def build_sources(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """UI-facing source cards (max one)."""
    if not hits:
        return []
    h = hits[0]
    return [
        {
            "name": h.get("name"),
            "description": h.get("description") or "",
            "tier": "",
            "image_url": h.get("image_url"),
            "wiki_link": h.get("wiki_link"),
            "drop_sources": list(h.get("drop_sources") or [])[:4],
        }
    ]


def answer(message: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    cfg, client = _get_client()
    history = list(history or [])

    if _is_price_query(message):
        reply = (
            "Operator, pricing and seller information is routed through the market subsystem, "
            "which is not connected to this knowledge interface yet. "
            "I can describe non-tradable items from my warframe-items corpus."
        )
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})
        return {"reply": reply, "sources": [], "history": history}

    pre_slug, pre_name = _resolve_query_slug(message)
    guard = _tradable_guard(pre_slug, pre_name)
    if guard and pre_slug and pre_slug not in load_alias_index()["docs_by_id"]:
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": guard})
        return {
            "reply": guard,
            "sources": [],
            "history": history,
            "resolved_slug": pre_slug,
            "equipment_class": "",
        }

    hits, _intent = retrieve(message)
    if hits:
        hits = [enrich_hit_drops(hits[0])]
    resolved_slug = hits[0].get("slug") or hits[0].get("doc_id") if hits else pre_slug
    equipment_class = hits[0].get("equipment_class") if hits else ""

    guard = _tradable_guard(resolved_slug, hits[0].get("name") if hits else pre_name)
    if guard:
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": guard})
        return {
            "reply": guard,
            "sources": [],
            "history": history,
            "resolved_slug": resolved_slug,
            "equipment_class": equipment_class,
        }

    context = _build_context(hits)

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_trim_history(history, cfg["max_history"]))
    messages.append(
        {
            "role": "user",
            "content": f"Knowledge context:\n{context}\n\nOperator query: {message}",
        }
    )

    response = client.chat.completions.create(
        model=cfg["chat_model"],
        messages=messages,
        temperature=cfg["temperature"],
    )
    reply = response.choices[0].message.content or ""

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": reply})

    return {
        "reply": reply,
        "sources": build_sources(hits),
        "history": history,
        "resolved_slug": resolved_slug,
        "equipment_class": equipment_class,
    }
