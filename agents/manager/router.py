"""Query routing — rules first, light LLM fallback."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from openai import OpenAI

from agents.market import search

_FORECAST_RE = re.compile(
    r"\b("
    r"forecast|predict|prediction|median|mean|trend|history|historical|"
    r"90\s*days?|48\s*hours?|timeframe|statistics|stats|"
    r"should i buy|should i sell|best time|when should|"
    r"price trend|moving avg|confidence interval"
    r")\b",
    re.I,
)

_LIVE_MARKET_RE = re.compile(
    r"\b("
    r"price|platinum|orders?|seller|buyers?|cheapest|spread|"
    r"who is selling|in-?game|live|order book|trading tax"
    r")\b",
    re.I,
)

_PORTFOLIO_RE = re.compile(
    r"\b(portfolio|holdings|my trades|trade history|log (a )?buy|log (a )?sell)\b",
    re.I,
)

_STRIP_WORDS = re.compile(
    r"\b("
    r"what|is|the|are|how|much|does|do|tell|me|about|show|find|get|"
    r"price|prices|order|orders|cheapest|sell|selling|buy|buying|"
    r"for|of|a|an|please|can|you|current|live|tier|rank"
    r")\b",
    re.I,
)

_CLASSIFIER_SYSTEM = """You classify Warframe assistant routing only. Return JSON with:
- primary_agent: "market" | "knowledge" | "forecasting"
- item_query: short item name to search on Warframe Market (empty if none)
- needs_forecast: boolean — true only for historical stats / trends / forecasts
- reason: one short phrase

Rules:
- Live sell/buy orders, sellers, platinum listings → market (needs_forecast false)
- Price history, median trends, forecasts, buy/sell timing analysis → forecasting (needs_forecast true)
- Item lore/stats/drops for items NOT on the market → knowledge
- Default tradable item questions → market unless needs_forecast is true
Do not answer the user question."""


@dataclass
class RoutePlan:
    agent: str  # market | knowledge | forecasting
    item_query: str = ""
    reason: str = ""


def _manager_model() -> str:
    return os.getenv("MANAGER_CHAT_MODEL", os.getenv("CHAT_MODEL", "gpt-4o-mini"))


def _normalize_query(text: str) -> str:
    return re.sub(r"[^\w\s'-]", " ", text).strip()


def _extract_item_query(message: str) -> str:
    text = _normalize_query(message.strip())
    if not text:
        return ""
    cleaned = _STRIP_WORDS.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    candidates = [text, cleaned]
    words = cleaned.split()
    if len(words) >= 2:
        candidates.append(" ".join(words[:4]))
    if len(words) >= 1:
        candidates.append(" ".join(words[-3:]))
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower()
        if not key or key in seen or len(key) < 2:
            continue
        seen.add(key)
        hits = search(candidate).get("results") or []
        if hits:
            return candidate
    return cleaned or text


def _wfm_has_item(message: str, item_query: str) -> bool:
    for q in (item_query, _normalize_query(message)):
        if not q.strip():
            continue
        if search(q.strip()).get("results"):
            return True
    return False


def _needs_llm_fallback(message: str, forecast: bool, live: bool) -> bool:
    if forecast and live:
        return True
    item_query = _extract_item_query(message)
    if not item_query and not forecast:
        return True
    return False


def _classify_with_llm(message: str) -> RoutePlan:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return RoutePlan(agent="market", item_query=_extract_item_query(message), reason="no_api_key_default_market")
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=_manager_model(),
        messages=[
            {"role": "system", "content": _CLASSIFIER_SYSTEM},
            {"role": "user", "content": message},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)
    agent = data.get("primary_agent", "market")
    if agent not in {"market", "knowledge", "forecasting"}:
        agent = "forecasting" if data.get("needs_forecast") else "market"
    if data.get("needs_forecast"):
        agent = "forecasting"
    return RoutePlan(
        agent=agent,
        item_query=str(data.get("item_query") or "").strip(),
        reason=str(data.get("reason") or "llm_classifier"),
    )


def classify(message: str) -> RoutePlan:
    text = (message or "").strip()
    forecast_hit = bool(_FORECAST_RE.search(text))
    portfolio_hit = bool(_PORTFOLIO_RE.search(text))
    live_hit = bool(_LIVE_MARKET_RE.search(text))

    if portfolio_hit and not forecast_hit:
        return RoutePlan(agent="market", reason="portfolio")

    if forecast_hit and not live_hit:
        return RoutePlan(agent="forecasting", reason="forecast_keywords")

    if _needs_llm_fallback(text, forecast_hit, live_hit):
        plan = _classify_with_llm(text)
        if plan.agent == "forecasting":
            return plan
        if plan.agent == "knowledge" or not _wfm_has_item(text, plan.item_query):
            if not _wfm_has_item(text, plan.item_query):
                return RoutePlan(agent="knowledge", item_query=plan.item_query, reason=plan.reason or "wfm_miss")
        return RoutePlan(agent="market", item_query=plan.item_query, reason=plan.reason or "llm_market")

    item_query = _extract_item_query(text)
    if _wfm_has_item(text, item_query):
        if forecast_hit:
            return RoutePlan(agent="forecasting", item_query=item_query, reason="forecast_over_live")
        return RoutePlan(agent="market", item_query=item_query, reason="wfm_hit")

    return RoutePlan(agent="knowledge", item_query=item_query, reason="wfm_miss")
