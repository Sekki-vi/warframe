"""Main query orchestration pipeline."""
from __future__ import annotations

import os
import re

from agents.forecasting.ask_agent import ask_market_question, item_names_from_result
from agents.knowledge.agent import answer as knowledge_answer
from agents.manager.guardrails import run_guardrails
from agents.manager.responses import format_knowledge_reply, knowledge_sources
from agents.manager.router import RoutePlan, classify
from agents.manager import session
from agents.market import answer as market_answer
from agents.market.tools.wfm_api import find_items_in_text
from agents.ranking.enrich import enrich_response


_FORECAST_FOLLOWUP_CUES = (
    "tell me more",
    "more detail",
    "more info",
    "explain",
    "break down",
    "break it down",
    "what about",
    "instead",
    "same item",
    "same one",
    "how confident",
    "confidence interval",
    "in depth",
    "full analysis",
)

_FOLLOWUP_PRONOUN_RE = re.compile(
    r"\b(she|her|he|him|it|they|them|that|this|those|these|same one|same item)\b",
    re.I,
)

_PRICE_FOLLOWUP_RE = re.compile(
    r"\b(how much|cost|costs|price|prices|platinum|cheapest|sell for|buy for)\b",
    re.I,
)


def _is_forecast_followup(message: str, session_id: str) -> bool:
    if not session.get_forecast_history(session_id):
        return False
    lowered = message.lower().strip()
    return any(cue in lowered for cue in _FORECAST_FOLLOWUP_CUES)


def _message_has_item(message: str) -> bool:
    normalized = re.sub(r"[^\w\s'-]", " ", message).strip()
    return bool(find_items_in_text(normalized))


def _looks_like_followup(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if _FOLLOWUP_PRONOUN_RE.search(text):
        return True
    if _PRICE_FOLLOWUP_RE.search(text) and not _message_has_item(text):
        return True
    return False


def _resolve_followup_message(message: str, plan: RoutePlan, meta: dict[str, str]) -> str:
    item = (plan.item_query or meta.get("last_item") or "").strip()
    if not item or _message_has_item(message):
        return message
    if not _looks_like_followup(message):
        return message
    return f"Regarding {item}: {message}"


def _should_use_knowledge_backup(message: str, market_result: dict) -> bool:
    if market_result.get("resolved_slug"):
        return False
    return True


def _item_from_result(result: dict, agent: str) -> tuple[str, str]:
    slug = str(result.get("resolved_slug") or "").strip()
    name = ""

    if agent == "knowledge":
        sources = result.get("sources") or []
        if sources and sources[0].get("name"):
            name = str(sources[0]["name"]).strip()
        elif slug:
            name = slug.replace("_", " ").title()
    elif agent == "market":
        slug = slug or str(result.get("resolved_slug") or "").strip()
        if slug and not name:
            name = slug.replace("_", " ").title()
    elif agent == "forecasting":
        names = item_names_from_result(result)
        if names:
            name = names[0]
    return name, slug


def _forecast_history_for_query(
    session_id: str,
    conversation: list[dict[str, str]],
    message: str,
) -> list[dict[str, str]]:
    forecast_history = session.get_forecast_history(session_id)
    if _message_has_item(message) or find_items_in_text(re.sub(r"[^\w\s'-]", " ", message).strip()):
        return forecast_history
    if not conversation:
        return forecast_history
    prefix = conversation[-8:]
    return prefix + forecast_history


def handle_query(message: str, user_id: str, session_id: str) -> dict:
    del user_id  # reserved for future auth
    guard = run_guardrails(message)
    if guard.blocked:
        return {
            "response": guard.message,
            "agents_called": [],
            "guardrail_flagged": True,
        }

    conversation = session.get_conversation(session_id)
    meta = session.get_session_meta(session_id)
    plan = classify(message, conversation=conversation, session_meta=meta)
    if _is_forecast_followup(message, session_id):
        plan = RoutePlan(agent="forecasting", reason="forecast_followup")

    resolved_message = _resolve_followup_message(message, plan, meta)

    agents_called: list[str] = []
    response = ""
    sources: list[dict] = []
    result: dict = {}
    record_agent = plan.agent
    disclaimer = (
        "Note: market forecasts are probabilistic estimates, not guaranteed trading advice.\n\n"
        if guard.flagged
        else ""
    )

    if plan.agent == "forecasting":
        chart_base = os.getenv("AGENT_PUBLIC_URL") or os.getenv("BACKEND_URL")
        history = _forecast_history_for_query(session_id, conversation, resolved_message)
        result = ask_market_question(resolved_message, history=history, base_url=chart_base)
        session.save_forecast_history(session_id, result.get("history") or history)
        response = disclaimer + (result.get("answer") or "")
        agents_called = ["forecasting"]
        record_agent = "forecasting"
    else:
        market_result = market_answer(
            resolved_message,
            session_id=session_id,
            history=conversation,
        )
        result = market_result
        response = disclaimer + (market_result.get("response") or "")
        agents_called = ["market"]
        if market_result.get("tier"):
            agents_called.append("ranking")
        record_agent = "market"

        if _should_use_knowledge_backup(message, market_result):
            k_history = session.get_conversation(session_id)
            k_result = enrich_response(knowledge_answer(resolved_message, history=k_history))
            if k_result.get("sources"):
                result = k_result
                response = disclaimer + format_knowledge_reply(k_result)
                sources = knowledge_sources(k_result)
                agents_called = ["market", "knowledge"]
                if k_result.get("tier"):
                    agents_called.append("ranking")
                record_agent = "knowledge"

    item_name, item_slug = _item_from_result(result, record_agent)
    session.append_turn(
        session_id,
        message,
        response,
        agent=record_agent,
        item_name=item_name,
        item_slug=item_slug,
    )

    out = {
        "response": response,
        "agents_called": agents_called,
        "guardrail_flagged": guard.flagged,
    }
    if plan.agent == "forecasting" and result.get("plot_url"):
        out["plot_url"] = result["plot_url"]
        names = item_names_from_result(result)
        out["chart_label"] = f"Forecast chart — {', '.join(names)}" if names else "Forecast chart"
    if sources:
        out["sources"] = sources
    return out
