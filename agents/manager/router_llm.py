"""LLM-based query routing for the Manager orchestrator."""
from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from agents.common import usage

CLASSIFIER_SYSTEM = """You route Warframe assistant queries. The ONLY routing decision you make is whether a query needs the Forecasting agent. Everything else is handled downstream: the Market agent answers by default and automatically falls back to Knowledge when an item is not on Warframe Market.

Return JSON with exactly these keys:
- needs_forecast: boolean
- item_query: short item name for Warframe Market search (empty if none)
- reason: one short phrase

Set needs_forecast TRUE only for:
- price history or price trends over time
- statistical analysis (median, mean, moving average, confidence interval)
- buy/sell timing advice ("when should I buy/sell", "is now a good time")
- investment / worth-over-time questions ("is it worth getting", "good investment", "should I buy or wait", "will the price go up")

Set needs_forecast FALSE for everything else, including: live prices, current buy/sell orders, sellers, cheapest listings, item tiers, recommendations, comparisons, lore, abilities, drops, quests, and portfolio/trade logging (including paraphrases like "what I own", "what I got", "my stuff", "my loot", "my collection", "what have I been buying").

Typos and casual language (yo, nah, u, ur, wut, wat) are fine — infer the intent, do not reject.

Use the routing_signals JSON provided with the user message. Resolve pronouns (she, he, it, they) and omitted item names from recent_conversation and session_meta.last_item, and set item_query from that prior context on follow-ups (e.g. "how much does she cost" after asking about Saryn Prime).

Do not answer the user question."""


def _manager_model() -> str:
    return os.getenv("MANAGER_CHAT_MODEL", os.getenv("CHAT_MODEL", "gpt-4o-mini"))


def classify_with_llm(message: str, context: dict[str, Any], item_query: str) -> dict[str, Any] | None:
    """Return routing JSON from the LLM, or None if no API key or the call fails."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    payload = json.dumps({"user_message": message, "routing_signals": context}, ensure_ascii=False)
    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=_manager_model(),
            messages=[
                {"role": "system", "content": CLASSIFIER_SYSTEM},
                {"role": "user", "content": payload},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        usage.record_response(resp, model=_manager_model(), agent="router")
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        if item_query and not data.get("item_query"):
            data["item_query"] = item_query
        return data
    except Exception:
        return None
