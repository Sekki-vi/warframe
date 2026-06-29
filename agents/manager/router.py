"""Query routing — hard rules first, then LLM classifier with routing signals."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agents.manager.router_llm import classify_with_llm
from agents.market import search
from agents.market.tools.wfm_api import find_items_in_text

_FORECAST_RE = re.compile(
    r"\b("
    r"forecast|predict|prediction|median|mean|trend|history|historical|"
    r"90\s*days?|48\s*hours?|timeframe|statistics|stats|"
    r"should i buy|should i sell|best time|good time|when should|"
    r"when to buy|when to sell|price trend|moving avg|confidence interval"
    r")\b",
    re.I,
)

_TIMING_RE = re.compile(
    r"\b("
    r"good time|best time|when to buy|when to sell|when is a|when should|"
    r"should i buy|should i sell|buy timing|sell timing"
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

_RECOMMEND_RE = re.compile(
    r"\b(recommend|recommendation|suggest|suggestion|best|good|top|which .+ should i)\b",
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

_FOLLOWUP_PRONOUN_RE = re.compile(
    r"\b(she|her|he|him|it|they|them|that|this|those|these|same one|same item)\b",
    re.I,
)

_PRICE_FOLLOWUP_RE = re.compile(
    r"\b(how much|cost|costs|price|prices|platinum|cheapest|sell for|buy for)\b",
    re.I,
)


def _looks_like_followup(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if _FOLLOWUP_PRONOUN_RE.search(text):
        return True
    if _PRICE_FOLLOWUP_RE.search(text) and not find_items_in_text(_normalize_query(text)):
        return True
    return False


def _followup_item_query(context: dict[str, Any]) -> str:
    item_query = str(context.get("item_query") or "").strip()
    if item_query:
        return item_query
    meta = context.get("session_meta") or {}
    return str(meta.get("last_item") or "").strip()
@dataclass
class RoutePlan:
    agent: str  # market | knowledge | forecasting
    item_query: str = ""
    reason: str = ""


def _normalize_query(text: str) -> str:
    return re.sub(r"[^\w\s'-]", " ", text).strip()


def _extract_item_query(message: str) -> str:
    text = _normalize_query(message.strip())
    if not text:
        return ""
    in_text = find_items_in_text(text)
    if in_text:
        return in_text[0]["name"]
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
            return hits[0].get("name") or candidate
    return cleaned or text


def _keyword_flags(text: str) -> dict[str, bool]:
    return {
        "forecast": bool(_FORECAST_RE.search(text)),
        "timing": bool(_TIMING_RE.search(text)),
        "live_market": bool(_LIVE_MARKET_RE.search(text)),
        "portfolio": bool(_PORTFOLIO_RE.search(text)),
        "recommend": bool(_RECOMMEND_RE.search(text)),
    }


def _warframe_routing_hint(message: str) -> dict[str, Any]:
    try:
        from agents.knowledge.agent import _frames_in_query, load_alias_index

        index = load_alias_index()
        frames = _frames_in_query(message, index)
    except Exception:
        return {
            "frames_mentioned": [],
            "warframe_variant": "none",
            "is_warframe_query": False,
        }

    if not frames:
        return {
            "frames_mentioned": [],
            "warframe_variant": "none",
            "is_warframe_query": False,
        }

    q = message.lower()
    has_prime_word = bool(re.search(r"\bprime\b", q))
    frames_mentioned = list(dict.fromkeys(name for _, name in frames))

    explicit_prime = any(
        re.search(rf"\b{re.escape((name or '').lower().replace(' prime', '').strip())}\s+prime\b", q)
        for _, name in frames
    )

    prime_slugs = [slug for slug, _ in frames if slug.endswith("_prime")]
    base_slugs = [slug for slug, _ in frames if not slug.endswith("_prime")]

    if explicit_prime:
        variant = "prime"
    elif has_prime_word and prime_slugs and base_slugs:
        variant = "ambiguous"
    elif has_prime_word and prime_slugs:
        variant = "prime"
    elif not has_prime_word:
        variant = "base"
    else:
        variant = "ambiguous"

    return {
        "frames_mentioned": frames_mentioned,
        "warframe_variant": variant,
        "is_warframe_query": True,
    }


def build_routing_context(
    message: str,
    conversation: list[dict[str, str]] | None = None,
    session_meta: dict[str, str] | None = None,
) -> dict[str, Any]:
    text = (message or "").strip()
    normalized = _normalize_query(text)
    wfm_matches = find_items_in_text(normalized)[:3]
    item_query = _extract_item_query(text)
    flags = _keyword_flags(text)
    frame_hint = _warframe_routing_hint(text)
    recent = [
        {"role": h["role"], "content": h["content"]}
        for h in (conversation or [])
        if h.get("role") in ("user", "assistant") and h.get("content")
    ][-10:]
    meta = dict(session_meta or {})
    return {
        "keyword_flags": flags,
        "wfm_matches": [{"name": i.get("name"), "slug": i.get("slug")} for i in wfm_matches],
        "item_query": item_query,
        "warframe": frame_hint,
        "recent_conversation": recent,
        "session_meta": meta,
    }


def _classify_fallback(message: str, context: dict[str, Any]) -> RoutePlan:
    text = (message or "").strip()
    flags = context.get("keyword_flags") or {}
    item_query = _followup_item_query(context)
    if not item_query:
        raw = context.get("item_query")
        item_query = str(raw if raw is not None else _extract_item_query(text))
    warframe = context.get("warframe") or {}
    variant = warframe.get("warframe_variant", "none")
    meta = context.get("session_meta") or {}
    last_item = str(meta.get("last_item") or "").strip()

    if flags.get("forecast") or flags.get("timing"):
        return RoutePlan(agent="forecasting", item_query=item_query, reason="fallback_forecast")
    if flags.get("portfolio"):
        return RoutePlan(agent="market", item_query=item_query, reason="fallback_portfolio")
    if flags.get("recommend"):
        return RoutePlan(agent="market", item_query=item_query, reason="recommend_market")
    if _looks_like_followup(text) and last_item:
        return RoutePlan(
            agent="market",
            item_query=last_item,
            reason="fallback_followup_context",
        )
    if variant == "prime":
        return RoutePlan(agent="market", item_query=item_query, reason="fallback_prime_warframe")
    if flags.get("live_market") and context.get("wfm_matches"):
        return RoutePlan(agent="market", item_query=item_query, reason="fallback_live_wfm")
    if context.get("wfm_matches"):
        return RoutePlan(agent="market", item_query=item_query, reason="fallback_wfm_hit")
    return RoutePlan(agent="market", item_query=item_query, reason="fallback_default_market")


def _plan_from_llm_data(
    data: dict[str, Any],
    fallback_item_query: str,
    context: dict[str, Any] | None = None,
) -> RoutePlan:
    agent = data.get("primary_agent", "market")
    if agent not in {"market", "knowledge", "forecasting"}:
        agent = "forecasting" if data.get("needs_forecast") else "market"
    if data.get("needs_forecast"):
        agent = "forecasting"
    reason = str(data.get("reason") or "llm_classifier")
    if agent == "knowledge" and context and context.get("wfm_matches"):
        agent = "market"
        reason = "llm_knowledge_overridden_wfm_hit"
    item_query = str(data.get("item_query") or fallback_item_query or "").strip()
    return RoutePlan(agent=agent, item_query=item_query, reason=reason)


def classify(
    message: str,
    *,
    conversation: list[dict[str, str]] | None = None,
    session_meta: dict[str, str] | None = None,
) -> RoutePlan:
    text = (message or "").strip()
    flags = _keyword_flags(text)
    forecast_hit = flags["forecast"]
    timing_hit = flags["timing"]
    portfolio_hit = flags["portfolio"]

    if portfolio_hit and not forecast_hit and not timing_hit:
        return RoutePlan(agent="market", reason="portfolio")

    if timing_hit or forecast_hit:
        item_query = _extract_item_query(text) or str((session_meta or {}).get("last_item") or "")
        return RoutePlan(
            agent="forecasting",
            item_query=item_query,
            reason="forecast_keywords",
        )

    context = build_routing_context(text, conversation, session_meta)
    item_query = _followup_item_query(context)

    plan = classify_with_llm(text, context, item_query)
    if plan is None:
        return _classify_fallback(text, context)

    return _plan_from_llm_data(plan, item_query, context)
