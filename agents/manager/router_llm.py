"""LLM-based query routing for the Manager orchestrator."""
from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

CLASSIFIER_SYSTEM = """You classify Warframe assistant routing only. Return JSON with exactly these keys:
- primary_agent: "market" | "knowledge" | "forecasting"
- item_query: short item name for Warframe Market search (empty if none)
- needs_forecast: boolean — true only for historical stats, trends, or buy/sell timing analysis
- is_warframe_query: boolean — true when the question is about a Warframe (not weapons/mods)
- warframe_variant: "prime" | "base" | "none" | "ambiguous"
- reason: one short phrase

Use the routing_signals JSON provided with the user message.

Primary policy — Market first:
- Default primary_agent: market for tradable items, prices, tiers, recommendations, suggestions, comparisons, and general trading questions
- Recommendations ("recommend", "best X to buy", "good shotgun", etc.) → market
- When routing_signals.wfm_matches is non-empty → market

Knowledge (backup only — orchestrator may still try Market first):
- knowledge only when wfm_matches is empty AND the query is clearly about non-tradable lore, drops, abilities, or quests (items not on Warframe Market)
- Do not route recommendations to knowledge

Hard constraints (must respect):
- needs_forecast true → primary_agent forecasting
- Live sell/buy orders, sellers, platinum listings, cheapest price → market (needs_forecast false)
- Portfolio / trade logging → market
- ANY phrasing that means "show me what I own/bought/have" → market (portfolio). Examples: "what I got", "my loot", "what do I have", "items I bought", "my stuff", "my collection", "what have I been buying", "show me my things", "give me my list" — all → market
- Forecast/timing keywords in signals with forecast or timing true are handled upstream; still set needs_forecast if the user wants trends or timing analysis
- Investment/worth questions ("is it worth getting", "good deal", "should I buy or wait") → needs_forecast true → forecasting
- Typos and casual language (yo, nah, u, ur, wut, wat) are fine — understand the intent, do not reject

Follow-up questions:
- Use recent_conversation and session_meta.last_item to resolve pronouns (she, he, it, they) and omitted item names
- Set item_query from prior context when the current message is a follow-up (e.g. "how much does she cost" after asking about Saryn Prime)
- Price/cost follow-ups → market with item_query from session_meta.last_item

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
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        if item_query and not data.get("item_query"):
            data["item_query"] = item_query
        return data
    except Exception:
        return None
