"""Market agent — live WFM orders, prices, seller activity, portfolio (library)."""
from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from agents.common import usage
from agents.market.tools.db import (
    add_holding,
    get_holdings,
    get_trade_history,
    init_db,
    remove_holding,
    sell_holding,
)
from agents.market.tools.wfm_api import get_item_details, get_orders, search_item
from agents.ranking.tier_store import lookup_tier_from_wfm

_sessions: dict[str, list[dict[str, Any]]] = {}
_session_meta: dict[str, dict[str, str]] = {}
_client: OpenAI | None = None
_db_ready = False

SYSTEM_PROMPT = """You are the Warframe Market trading sub-agent.
Scope: live buy/sell orders, prices, seller activity (in-game status), item tiers,
portfolio, and trading recommendations. Forecasting/price-history is another agent's job.
Currency: platinum (p). Be concise; include seller active status when showing orders.

Recommendations: use your own Warframe knowledge to name the best-fitting tradable item
(e.g. toxic frame -> Saryn, tank -> Rhino/Inaros, beginner shotgun -> Hek), then resolve it
with search_item and add tier/price. Never answer a "recommend / which / what's a good"
question with "I don't know" — pick a concrete item.

Out of scope: for lore, identity, abilities, mechanics, quests, or drop locations
("who is X", "tell me about X", etc.) call defer_to_knowledge with a short reason and stop.
Do not answer those yourself and never tell the user to consult another source."""

TOOLS = [
    {"type": "function", "function": {"name": "search_item", "description": "Find items by name; returns slug + name.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_orders", "description": "Top-5 live buy/sell orders (seller, price, qty, active).", "parameters": {"type": "object", "properties": {"item_slug": {"type": "string"}}, "required": ["item_slug"]}}},
    {"type": "function", "function": {"name": "get_item_details", "description": "Item info: name, image, description, MR, ducats, tags, vaulted.", "parameters": {"type": "object", "properties": {"item_slug": {"type": "string"}}, "required": ["item_slug"]}}},
    {"type": "function", "function": {"name": "lookup_tier", "description": "Overframe tier S–D for an item slug.", "parameters": {"type": "object", "properties": {"item_slug": {"type": "string"}}, "required": ["item_slug"]}}},
    {"type": "function", "function": {"name": "add_holding", "description": "Log a portfolio purchase.", "parameters": {"type": "object", "properties": {"item_slug": {"type": "string"}, "item_name": {"type": "string"}, "quantity": {"type": "integer"}, "price_per_unit": {"type": "number"}}, "required": ["item_slug", "item_name", "quantity", "price_per_unit"]}}},
    {"type": "function", "function": {"name": "sell_holding", "description": "Log a portfolio sale (with P&L).", "parameters": {"type": "object", "properties": {"item_slug": {"type": "string"}, "quantity": {"type": "integer"}, "price_per_unit": {"type": "number"}}, "required": ["item_slug", "quantity", "price_per_unit"]}}},
    {"type": "function", "function": {"name": "get_holdings", "description": "Current portfolio holdings.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_trade_history", "description": "Recent trade history.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "defer_to_knowledge", "description": "Defer an out-of-scope question (lore/abilities/quests/drops) to the Knowledge agent. Don't call other tools when deferring.", "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}}},
]

# Cap how much prior conversation is replayed to the market model each call —
# the tool-calling loop re-sends the whole message list on every round-trip.
_MAX_MARKET_HISTORY_MSGS = 6


def _ensure_db() -> None:
    global _db_ready
    if not _db_ready:
        init_db()
        _db_ready = True


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for market answer()")
        _client = OpenAI(api_key=api_key)
    return _client


def _chat_model() -> str:
    return os.getenv("MARKET_CHAT_MODEL", os.getenv("CHAT_MODEL", "gpt-4o-mini"))


def _meta(session_id: str) -> dict[str, str]:
    if session_id not in _session_meta:
        _session_meta[session_id] = {
            "tier": "",
            "resolved_slug": "",
            "item_name": "",
            "needs_knowledge": False,
        }
    return _session_meta[session_id]


def _resolve_tier(meta: dict[str, str], slug: str, tags: list[str] | None = None) -> None:
    if not slug:
        return
    if tags is None:
        try:
            details = get_item_details(slug)
            tags = details.get("tags") or []
            if details.get("name"):
                meta["item_name"] = str(details["name"])
        except Exception:
            tags = []
    tier = lookup_tier_from_wfm(slug, tags or [])
    if tier:
        meta["tier"] = tier


def _build_item_source(slug: str) -> dict[str, Any] | None:
    try:
        details = get_item_details(slug)
    except Exception:
        return None
    tier = lookup_tier_from_wfm(slug, details.get("tags") or [])
    return {
        "name": details.get("name") or slug.replace("_", " ").title(),
        "description": details.get("description") or "",
        "tier": tier,
        "image_url": details.get("image_url") or "",
        "wiki_link": details.get("wiki_link") or "",
        "drop_sources": [],
    }


def _dispatch(name: str, args: dict[str, Any], session_id: str) -> str:
    meta = _meta(session_id)
    if name in {"add_holding", "sell_holding", "get_holdings", "get_trade_history"}:
        _ensure_db()
    if name == "search_item":
        results = search_item(**args)
        if results:
            slug = results[0].get("slug") or ""
            meta["resolved_slug"] = slug
            _resolve_tier(meta, slug)
        return json.dumps(results)
    if name == "get_orders":
        slug = args.get("item_slug") or ""
        if slug:
            meta["resolved_slug"] = slug
            _resolve_tier(meta, slug)
        return json.dumps(get_orders(**args))
    if name == "get_item_details":
        details = get_item_details(**args)
        slug = details.get("slug") or args.get("item_slug") or ""
        if slug:
            meta["resolved_slug"] = slug
            if details.get("name"):
                meta["item_name"] = str(details["name"])
            _resolve_tier(meta, slug, details.get("tags") or [])
        return json.dumps(details)
    if name == "lookup_tier":
        slug = args.get("item_slug") or ""
        details = get_item_details(slug)
        tier = lookup_tier_from_wfm(slug, details.get("tags") or [])
        meta["resolved_slug"] = slug
        if details.get("name"):
            meta["item_name"] = str(details["name"])
        if tier:
            meta["tier"] = tier
        return json.dumps({"slug": slug, "tier": tier or "unknown"})
    if name == "add_holding":
        return add_holding(**args)
    if name == "sell_holding":
        return sell_holding(**args)
    if name == "get_holdings":
        return json.dumps(get_holdings())
    if name == "get_trade_history":
        return json.dumps(get_trade_history(**args))
    if name == "defer_to_knowledge":
        meta["needs_knowledge"] = True
        return json.dumps({"status": "deferred", "reason": args.get("reason") or ""})
    return f"Unknown tool: {name}"


def _seed_session_from_history(session_id: str, history: list[dict[str, str]] | None) -> None:
    if session_id in _sessions:
        return
    _sessions[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history or []:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            _sessions[session_id].append({"role": role, "content": str(content)})


def _run_agent(message: str, session_id: str, history: list[dict[str, str]] | None = None) -> str:
    _seed_session_from_history(session_id, history)
    if session_id not in _sessions:
        _sessions[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    _meta(session_id).update(
        {"tier": "", "resolved_slug": "", "item_name": "", "needs_knowledge": False}
    )
    _sessions[session_id].append({"role": "user", "content": message})
    # Replay only the system prompt + the most recent turns to keep prompt
    # tokens bounded on long sessions (within-query tool messages are appended
    # to `messages` below and are not capped).
    history_msgs = _sessions[session_id]
    messages = [history_msgs[0]] + history_msgs[1:][-_MAX_MARKET_HISTORY_MSGS:]
    client = _get_client()
    while True:
        resp = client.chat.completions.create(
            model=_chat_model(),
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        usage.record_response(resp, model=_chat_model(), agent="market")
        msg = resp.choices[0].message
        messages.append(msg)
        if not msg.tool_calls:
            _sessions[session_id].append({"role": "assistant", "content": msg.content or ""})
            return msg.content or ""
        for tc in msg.tool_calls:
            result = _dispatch(tc.function.name, json.loads(tc.function.arguments), session_id)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
    _session_meta.pop(session_id, None)


def answer(
    message: str,
    session_id: str = "default",
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Natural-language market query (orders, prices, portfolio)."""
    reply = _run_agent(message, session_id, history=history)
    meta = _meta(session_id)
    out: dict[str, Any] = {
        "response": reply,
        "session_id": session_id,
        "needs_knowledge": bool(meta.get("needs_knowledge")),
    }
    slug = meta.get("resolved_slug") or ""
    if slug:
        out["resolved_slug"] = slug
        source = _build_item_source(slug)
        if source:
            out["sources"] = [source]
            if source.get("tier"):
                out["tier"] = source["tier"]
    elif meta.get("tier"):
        out["tier"] = meta["tier"]
    return out


def search(query: str) -> dict[str, Any]:
    results = search_item(query)
    return {"results": results}


def item_details(slug: str) -> dict[str, Any]:
    return get_item_details(slug)


def orders(slug: str) -> dict[str, Any]:
    return get_orders(slug)


def get_portfolio() -> dict[str, Any]:
    _ensure_db()
    return {"holdings": get_holdings()}


def get_trades(limit: int = 20) -> dict[str, Any]:
    _ensure_db()
    return {"trades": get_trade_history(limit=limit)}


def buy(
    item_slug: str,
    item_name: str,
    quantity: int,
    price_per_unit: float,
) -> dict[str, Any]:
    _ensure_db()
    message = add_holding(item_slug, item_name, quantity, price_per_unit)
    return {"status": "ok", "message": message}


def sell(item_slug: str, quantity: int, price_per_unit: float) -> dict[str, Any]:
    _ensure_db()
    message = sell_holding(item_slug, quantity, price_per_unit)
    if message.startswith("Error"):
        return {"status": "error", "message": message}
    return {"status": "ok", "message": message}


def remove(item_slug: str) -> dict[str, Any]:
    """Delete a holding outright (no sell trade logged)."""
    _ensure_db()
    message = remove_holding(item_slug)
    if message.startswith("Error"):
        return {"status": "error", "message": message}
    return {"status": "ok", "message": message}
