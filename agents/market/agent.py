"""Market agent — live WFM API queries via function calling."""
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from agents.market.tools import TOOL_DEFINITIONS, execute_tool, tool_result_json
from chat.config import get_chat_config

MARKET_SYSTEM = """You are the Warframe Market data subsystem. Fetch LIVE data only from tools.

Rules:
- Always resolve the item slug before fetching orders if slug is uncertain.
- Return seller in-game names (IGN) for trading; operators whisper via /w <name>.
- Prices are in platinum (p).
- If no orders found, say the item may not be listed or slug may be wrong.
- Never invent prices or sellers.
"""

_client: OpenAI | None = None
_cfg: dict | None = None


def _get_client() -> tuple[dict, OpenAI]:
    global _client, _cfg
    if _cfg is None:
        _cfg = get_chat_config()
        _client = OpenAI(api_key=_cfg["openai_key"])
    return _cfg, _client


def run_orders_query(request: str, *, wfm_slug: str | None = None) -> dict[str, Any]:
    """Run market agent tool loop for a market-related sub-request."""
    cfg, client = _get_client()
    user_content = request
    if wfm_slug:
        user_content += f"\n\nHint: WFM slug from knowledge base: {wfm_slug}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": MARKET_SYSTEM},
        {"role": "user", "content": user_content},
    ]

    orders: list[dict[str, Any]] = []
    price_summary: dict[str, Any] | None = None
    resolved_slug: str | None = wfm_slug or None
    reply = ""

    for _ in range(3):
        response = client.chat.completions.create(
            model=cfg["chat_model"],
            messages=messages,
            tools=TOOL_DEFINITIONS,
            temperature=0.1,
        )
        msg = response.choices[0].message
        if not msg.tool_calls:
            reply = msg.content or ""
            break

        messages.append(msg)
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            result = execute_tool(call.function.name, args)
            if call.function.name == "resolve_item_slug" and result.get("slug"):
                resolved_slug = result["slug"]
            if call.function.name == "get_live_orders" and isinstance(result, list):
                orders = result
            if call.function.name == "get_price_summary":
                price_summary = result
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": tool_result_json(result),
                }
            )

    if not reply and messages:
        last = messages[-1]
        if last.get("role") == "assistant":
            reply = last.get("content") or ""

    return {
        "slug": resolved_slug,
        "orders": orders,
        "price_summary": price_summary,
        "reply": reply,
        "market_context": reply,
    }


# Backward-compatible alias
run = run_orders_query
