"""OpenAI tool definitions and handlers for live market data."""
from __future__ import annotations

import json
from typing import Any

from agents.market import client

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "resolve_item_slug",
            "description": "Resolve a Warframe item name to its warframe.market url_name slug.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_or_slug": {"type": "string", "description": "Item name or slug"},
                },
                "required": ["name_or_slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_live_orders",
            "description": "Get current buy or sell orders for an item on warframe.market.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "order_type": {"type": "string", "enum": ["sell", "buy"], "default": "sell"},
                    "rank": {"type": "integer", "description": "Mod rank if applicable"},
                    "subtype": {"type": "string", "description": "Relic/riven subtype if applicable"},
                    "max_platinum": {"type": "integer"},
                    "online_only": {"type": "boolean", "default": False},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_price_summary",
            "description": "Get live price summary (cheapest sell, highest buy, statistics) for an item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "rank": {"type": "integer"},
                    "subtype": {"type": "string"},
                },
                "required": ["slug"],
            },
        },
    },
]

ORCHESTRATOR_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_market",
            "description": (
                "Fetch live warframe.market prices, orders, or sellers. "
                "Use when the operator asks about current prices, cheapest sellers, "
                "who is selling, buy orders, or trading."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": "What to look up, including item name, rank, price filters",
                    },
                    "wfm_slug": {
                        "type": "string",
                        "description": "Known WFM slug from knowledge context if available",
                    },
                },
                "required": ["request"],
            },
        },
    },
]


def execute_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name == "resolve_item_slug":
        slug = client.resolve_slug(arguments["name_or_slug"])
        return {"slug": slug, "query": arguments["name_or_slug"]}
    if name == "get_live_orders":
        return client.get_live_orders(
            arguments["slug"],
            order_type=arguments.get("order_type", "sell"),
            rank=arguments.get("rank"),
            subtype=arguments.get("subtype"),
            max_platinum=arguments.get("max_platinum"),
            online_only=arguments.get("online_only", False),
            limit=arguments.get("limit", 10),
        )
    if name == "get_price_summary":
        return client.get_price_summary(
            arguments["slug"],
            rank=arguments.get("rank"),
            subtype=arguments.get("subtype"),
        )
    return {"error": f"Unknown tool: {name}"}


def tool_result_json(result: Any) -> str:
    return json.dumps(result, ensure_ascii=False, default=str)
