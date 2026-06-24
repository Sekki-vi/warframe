"""Knowledge Agent — WFI-only Ordis sub-agent."""
from __future__ import annotations

import re
from typing import Any

from openai import OpenAI

from agents.knowledge.intent import QueryIntent, parse_query_intent
from agents.knowledge.keyword import keyword_search
from agents.knowledge.merge import merge_hits
from agents.knowledge.semantic import semantic_search
from chat.config import get_chat_config

SYSTEM_PROMPT = """You are Ordis, a Cephalon knowledge subsystem aboard a Tenno's Orbiter.

Persona:
- Formal, helpful, and slightly dramatic in a sci-fi manner.
- Address the user as "Operator" occasionally.

Rules:
- Answer ONLY using the provided knowledge context. If context is insufficient, say so clearly.
- Never mention prices, platinum, sellers, orders, or warframe.market listings.
- If asked about prices or trading, explain that market data is handled by a separate subsystem (not yet connected).
- For recommendation requests, discuss ONLY the items in the knowledge context (typically up to 3). Give brief stats from context.
- For random item requests, discuss ONLY the single item in context.
- When recommending weapons, list WEAPONS only — not mods — unless the Operator explicitly asked for mods.
- Never invent item stats or names not present in the context.
"""

_client: OpenAI | None = None
_cfg: dict | None = None


def _get_client() -> tuple[dict, OpenAI]:
    global _client, _cfg
    if _cfg is None:
        _cfg = get_chat_config()
        _client = OpenAI(api_key=_cfg["openai_key"])
    return _cfg, _client


def _trim_history(history: list[dict[str, str]], max_turns: int) -> list[dict[str, str]]:
    if len(history) <= max_turns * 2:
        return history
    return history[-(max_turns * 2) :]


def _build_context(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "No relevant items were retrieved from the knowledge base."
    blocks: list[str] = []
    for i, hit in enumerate(hits, 1):
        parts = [f"[{i}] {hit.get('name')}"]
        if hit.get("tier"):
            parts[0] += f" (tier: {hit.get('tier')})"
        if hit.get("text"):
            parts.append(hit["text"])
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def _is_price_query(query: str) -> bool:
    q = query.lower()
    return bool(
        re.search(
            r"\b(price|platinum|cost|how much|sell|buy|seller|trade|market|who is selling)\b",
            q,
        )
    )


def _semantic_top_k(intent: QueryIntent) -> int:
    if intent.kind in ("random", "single"):
        return 1
    if intent.kind == "recommend":
        return min(3, intent.result_count)
    return 5


def retrieve(query: str) -> tuple[list[dict[str, Any]], QueryIntent]:
    intent = parse_query_intent(query)
    keyword_hits = keyword_search(query, intent)
    if intent.kind == "single" or (
        keyword_hits and keyword_hits[0].get("source") == "exact"
    ):
        return keyword_hits[:1], intent
    if intent.tier_filter or (
        intent.variant and intent.kind in ("recommend", "random", "lookup")
    ):
        return keyword_hits[: intent.result_count], intent
    semantic_hits = semantic_search(query, top_k=_semantic_top_k(intent))
    hits = merge_hits(keyword_hits, semantic_hits, max_results=intent.result_count)
    return hits, intent


def build_sources(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """UI-facing source cards."""
    return [
        {
            "name": h.get("name"),
            "description": h.get("description") or "",
            "tier": h.get("tier") or "",
            "image_url": h.get("image_url"),
            "wiki_link": h.get("wiki_link"),
        }
        for h in hits
    ]


def answer(message: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    cfg, client = _get_client()
    history = list(history or [])

    if _is_price_query(message):
        reply = (
            "Operator, pricing and seller information is routed through the market subsystem, "
            "which is not connected to this knowledge interface yet. "
            "I can describe items, stats, and drop locations from my warframe-items corpus. "
            "What item would you like to know about?"
        )
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})
        return {"reply": reply, "sources": [], "history": history}

    hits, intent = retrieve(message)
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

    sources = build_sources(hits)

    return {"reply": reply, "sources": sources, "history": history}
