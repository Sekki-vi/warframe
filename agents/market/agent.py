"""Market agent — live WFM orders, prices, seller activity, portfolio (library)."""
from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from agents.market.tools.db import (
    add_holding,
    get_holdings,
    get_trade_history,
    init_db,
    sell_holding,
)
from agents.market.tools.wfm_api import get_item_details, get_orders, search_item
from agents.ranking.tier_store import lookup_tier_from_wfm

_sessions: dict[str, list[dict[str, Any]]] = {}
_session_meta: dict[str, dict[str, str]] = {}
_client: OpenAI | None = None
_db_ready = False

SYSTEM_PROMPT = """You are a Warframe Market trading sub-agent in a multi-agent pipeline.
Scope: live buy/sell orders, current prices, seller activity (are they in-game), portfolio management.
You do NOT handle forecasting or price history — that is the Forecasting Agent's job.
When the user asks about item quality or tier, call lookup_tier after resolving the item slug.
Return structured, concise answers. Always include seller active status when showing orders.
Currency: platinum (p)."""

TOOLS = [
    {"type": "function", "function": {"name": "search_item", "description": "Search items by name. Returns slug + display name.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_orders", "description": "Live top-5 buy/sell orders. Includes seller name, price, quantity, and active status.", "parameters": {"type": "object", "properties": {"item_slug": {"type": "string"}}, "required": ["item_slug"]}}},
    {"type": "function", "function": {"name": "get_item_details", "description": "Full item info: name, image_url, description, mastery rank, ducats, tags, vaulted.", "parameters": {"type": "object", "properties": {"item_slug": {"type": "string"}}, "required": ["item_slug"]}}},
    {"type": "function", "function": {"name": "lookup_tier", "description": "Overframe tier S–D for a tradable item slug.", "parameters": {"type": "object", "properties": {"item_slug": {"type": "string"}}, "required": ["item_slug"]}}},
    {"type": "function", "function": {"name": "add_holding", "description": "Log a purchase to portfolio.", "parameters": {"type": "object", "properties": {"item_slug": {"type": "string"}, "item_name": {"type": "string"}, "quantity": {"type": "integer"}, "price_per_unit": {"type": "number"}}, "required": ["item_slug", "item_name", "quantity", "price_per_unit"]}}},
    {"type": "function", "function": {"name": "sell_holding", "description": "Log a sale from portfolio with P&L.", "parameters": {"type": "object", "properties": {"item_slug": {"type": "string"}, "quantity": {"type": "integer"}, "price_per_unit": {"type": "number"}}, "required": ["item_slug", "quantity", "price_per_unit"]}}},
    {"type": "function", "function": {"name": "get_holdings", "description": "Return current portfolio holdings.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_trade_history", "description": "Return recent trade history.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}}},
]


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
        _session_meta[session_id] = {"tier": "", "resolved_slug": ""}
    return _session_meta[session_id]


def _dispatch(name: str, args: dict[str, Any], session_id: str) -> str:
    meta = _meta(session_id)
    if name in {"add_holding", "sell_holding", "get_holdings", "get_trade_history"}:
        _ensure_db()
    if name == "search_item":
        results = search_item(**args)
        if results:
            meta["resolved_slug"] = results[0].get("slug") or ""
        return json.dumps(results)
    if name == "get_orders":
        slug = args.get("item_slug") or ""
        if slug:
            meta["resolved_slug"] = slug
        return json.dumps(get_orders(**args))
    if name == "get_item_details":
        details = get_item_details(**args)
        slug = details.get("slug") or args.get("item_slug") or ""
        if slug:
            meta["resolved_slug"] = slug
        return json.dumps(details)
    if name == "lookup_tier":
        slug = args.get("item_slug") or ""
        details = get_item_details(slug)
        tier = lookup_tier_from_wfm(slug, details.get("tags") or [])
        meta["resolved_slug"] = slug
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
    return f"Unknown tool: {name}"


def _run_agent(message: str, session_id: str) -> str:
    if session_id not in _sessions:
        _sessions[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    _meta(session_id).update({"tier": "", "resolved_slug": ""})
    _sessions[session_id].append({"role": "user", "content": message})
    messages = list(_sessions[session_id])
    client = _get_client()
    while True:
        resp = client.chat.completions.create(
            model=_chat_model(),
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
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


def answer(message: str, session_id: str = "default") -> dict[str, Any]:
    """Natural-language market query (orders, prices, portfolio)."""
    reply = _run_agent(message, session_id)
    meta = _meta(session_id)
    out: dict[str, Any] = {"response": reply, "session_id": session_id}
    if meta.get("tier"):
        out["tier"] = meta["tier"]
    if meta.get("resolved_slug"):
        out["resolved_slug"] = meta["resolved_slug"]
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
