"""RAG chat service with Ordis Cephalon persona."""
from __future__ import annotations

from typing import Any

from openai import OpenAI

from chat.config import get_chat_config
from chat.rag_query import search

SYSTEM_PROMPT = """You are Ordis, a Cephalon aboard a Tenno's Orbiter, operating the Warframe Market interface.

Persona:
- Formal, helpful, and slightly dramatic in a sci-fi manner.
- Address the user as "Operator" occasionally.
- Keep answers concise but informative.

Rules:
- Answer ONLY using the retrieved context provided below. If the context does not contain enough information, say so clearly.
- When mentioning prices, always cite the price_snapshot_date from the context.
- Warn that price data is from a historical snapshot and may be stale; suggest checking warframe.market for current listings.
- If asked about specific sellers, in-game whispers, or connecting to trade with a player, explain that seller lookup is not yet available in this interface and direct them to warframe.market.
- Never invent item stats, prices, or seller names not present in the context.
"""

_client: OpenAI | None = None
_cfg: dict | None = None


def _get_client() -> tuple[dict, OpenAI]:
    global _client, _cfg
    if _cfg is None:
        _cfg = get_chat_config()
        _client = OpenAI(api_key=_cfg["openai_key"])
    return _cfg, _client


def _format_rank(rank: int | None) -> str:
    if rank is None:
        return "unranked"
    return f"rank {rank}"


def _build_context(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "No relevant items were retrieved from the market database."

    blocks: list[str] = []
    for i, src in enumerate(sources, 1):
        parts = [
            f"[Source {i}] {src.get('item_name') or src.get('slug')} "
            f"({src.get('slug')}, {_format_rank(src.get('rank'))}"
        ]
        if src.get("subtype"):
            parts[0] += f", subtype: {src['subtype']}"
        parts[0] += ")"
        if src.get("category"):
            parts.append(f"Category: {src['category']}")
        if src.get("text"):
            parts.append(src["text"])
        if src.get("sell_median") is not None:
            parts.append(f"Sell median: {src['sell_median']} platinum")
        if src.get("buy_median") is not None:
            parts.append(f"Buy median: {src['buy_median']} platinum")
        if src.get("price_snapshot_date"):
            parts.append(f"Price snapshot date: {src['price_snapshot_date']}")
        if src.get("wiki_link"):
            parts.append(f"Wiki: {src['wiki_link']}")
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def _trim_history(history: list[dict[str, str]], max_turns: int) -> list[dict[str, str]]:
    """Keep at most max_turns user/assistant pairs."""
    if len(history) <= max_turns * 2:
        return history
    return history[-(max_turns * 2) :]


def chat(message: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Run RAG pipeline: retrieve sources, then generate Ordis reply."""
    cfg, client = _get_client()
    history = list(history or [])

    sources = search(message, top_k=cfg["top_k"])
    context = _build_context(sources)

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_trim_history(history, cfg["max_history"]))
    messages.append(
        {
            "role": "user",
            "content": f"Retrieved context:\n{context}\n\nOperator query: {message}",
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

    snapshot = sources[0].get("price_snapshot_date") if sources else None
    return {
        "reply": reply,
        "sources": sources,
        "snapshot_date": snapshot,
        "history": history,
    }
