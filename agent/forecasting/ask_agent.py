"""Natural-language Q&A over Warframe Market forecasts."""

from __future__ import annotations

import json
import re
from typing import Any

from .llm_client import LLMConfigError, chat_json, chat_text, get_model
from .warframe_forecast_agent import WarframeMarketError, compare_items, forecast_item

EXTRACTION_SYSTEM = """You extract structured forecast requests from user questions about Warframe Market prices.

Return JSON with exactly these keys:
- skill: "forecast_item" or "compare_items"
- items: array of Warframe Market item names mentioned (strings)
- timeframe: "90days" or "48hours" (default 90days unless user asks for recent/short-term)
- price_field: one of median, avg_price, wa_price, closed_price, moving_avg (default median unless user names another)
- horizon: integer forecast steps ahead (default 12; if user mentions days, approximate: 6 days -> 6, 2 days -> 4)
- intent: short label such as buy_timing, sell_timing, price_check, trend, compare, general

Rules:
- If two or more items are mentioned for comparison, use compare_items.
- Resolve informal item names to likely Warframe Market names (e.g. "mag prime" -> "Mag Prime Set").
- Do not answer the question; only extract the plan.
"""

NARRATIVE_SYSTEM = """You are the narrative layer for a Warframe Market forecasting subagent.

You receive:
1) the user's original question
2) structured forecast/compare results computed from real market statistics (not invented)

Write a clear, human-friendly answer in plain English that:
- Directly addresses the user's question
- Cites specific numbers from the data (last price, median, mean, forecast mean, confidence intervals)
- For buy/sell timing questions, give a cautious suggestion based on forecast direction, drift, and bands
- Mention the chart URL if provided
- Use short paragraphs and bullet points when helpful

Constraints:
- Ground every claim in the provided data. Do not invent prices or trends.
- This is probabilistic market analysis, not guaranteed trading advice. Say that once, briefly.
- Forecast steps are model time steps on downsampled history, not exact calendar hours unless the data window makes that clear.
- If uncertainty is high (wide confidence bands), say so.
"""


def _looks_like_question(text: str) -> bool:
    lowered = text.lower()
    if "?" in text:
        return True
    cues = (
        "best time",
        "when should",
        "should i buy",
        "should i sell",
        "what is the price",
        "what's the price",
        "how much",
        "compare",
        " versus ",
        " vs ",
        "forecast",
        "predict",
        "median",
        "mean",
        "cheaper",
    )
    return any(cue in lowered for cue in cues)


def extract_plan(question: str) -> dict[str, Any]:
    plan = chat_json(EXTRACTION_SYSTEM, question)
    skill = plan.get("skill", "forecast_item")
    if skill not in {"forecast_item", "compare_items"}:
        skill = "compare_items" if len(plan.get("items") or []) >= 2 else "forecast_item"
        plan["skill"] = skill

    items = plan.get("items") or []
    if isinstance(items, str):
        items = [items]
    plan["items"] = [str(item).strip() for item in items if str(item).strip()]

    plan.setdefault("timeframe", "90days")
    plan.setdefault("price_field", "median")
    plan.setdefault("horizon", 12)
    plan.setdefault("intent", "general")
    plan["horizon"] = max(1, min(int(plan["horizon"]), 120))
    return plan


def generate_answer(question: str, result: dict[str, Any], plan: dict[str, Any]) -> str:
    compact = {
        "question": question,
        "intent": plan.get("intent"),
        "skill": result.get("skill"),
        "plot_url": result.get("plot_url"),
        "unit_label": result.get("unit_label"),
        "item": result.get("item"),
        "market": result.get("market"),
        "stats": result.get("stats"),
        "items": result.get("items"),
        "comparison": result.get("comparison"),
    }
    user_payload = json.dumps(compact, indent=2)
    return chat_text(
        NARRATIVE_SYSTEM,
        f"User question:\n{question}\n\nStructured forecast data:\n{user_payload}",
    )


def ask_market_question(
    question: str,
    *,
    base_url: str | None = None,
    timeframe: str | None = None,
    price_field: str | None = None,
    horizon: int | None = None,
    points: int = 60,
    paths: int = 5000,
    recent_frac: float = 0.35,
    seed: int = 42,
) -> dict[str, Any]:
    """Answer a natural-language market question using forecast tools + an LLM."""
    question = question.strip()
    if not question:
        raise WarframeMarketError("Provide a question about Warframe Market prices")

    try:
        plan = extract_plan(question)
    except LLMConfigError:
        raise
    except Exception as exc:
        raise WarframeMarketError(f"Could not interpret question: {exc}") from exc

    if timeframe:
        plan["timeframe"] = timeframe
    if price_field:
        plan["price_field"] = price_field
    if horizon is not None:
        plan["horizon"] = horizon

    items = plan["items"]
    if not items:
        raise WarframeMarketError(
            "Could not identify a Warframe Market item in your question. "
            "Try naming the item explicitly, e.g. 'Mag Prime Set'."
        )

    kwargs = {
        "timeframe": plan["timeframe"],
        "price_field": plan["price_field"],
        "points": points,
        "horizon": plan["horizon"],
        "paths": paths,
        "recent_frac": recent_frac,
        "seed": seed,
        "base_url": base_url,
    }

    if plan["skill"] == "compare_items":
        if len(items) < 2:
            raise WarframeMarketError("Compare questions need at least two items")
        result = compare_items(items, **kwargs)
    else:
        result = forecast_item(items[0], **kwargs)

    try:
        answer = generate_answer(question, result, plan)
    except LLMConfigError:
        raise
    except Exception as exc:
        raise WarframeMarketError(f"Forecast succeeded but narrative generation failed: {exc}") from exc

    result["skill"] = "ask_market_question"
    result["question"] = question
    result["plan"] = plan
    result["answer"] = answer
    result["llm_model"] = get_model()
    result["agent"] = "warframe_forecasting_agent"
    return result


def maybe_item_name_only(text: str) -> bool:
    """True when text is likely just an item name, not a full question."""
    text = text.strip()
    if not text or _looks_like_question(text):
        return False
    return len(text.split()) <= 6 and not re.search(r"\d", text)
