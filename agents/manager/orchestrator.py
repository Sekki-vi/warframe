"""Main query orchestration pipeline."""
from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

from agents.common import usage
from agents.forecasting.ask_agent import ask_market_question, item_names_from_result
from agents.knowledge.agent import answer as knowledge_answer
from agents.manager.guardrails import check_outgoing, run_guardrails
from agents.manager.responses import format_knowledge_reply, knowledge_sources, market_sources
from agents.manager.router import RoutePlan, classify, is_recommendation_query
from agents.manager import session
from agents.market import answer as market_answer
from agents.market.tools.wfm_api import find_items_in_text
from agents.ranking.enrich import enrich_response

logger = logging.getLogger("warframe.router")


_MULTI_LIVE_RE = re.compile(
    r"\b(current\s+price|right\s+now|who\s+is\s+selling|live\s+(price|order)|"
    r"cheapest\s+(now|today)|orders?\s+(now|today|right\s+now)|currently\s+(selling|listed))\b",
    re.I,
)
_MULTI_FORECAST_RE = re.compile(
    r"\b(forecast|predict|next\s+week|next\s+month|invest|investment|"
    r"price\s+in\s+\d|will\s+(it|the\s+price)|going\s+up|going\s+down|trend|"
    r"worth\s+(getting|buying|it)|should\s+i\s+buy|should\s+i\s+wait|"
    r"good\s+(investment|deal|time)|buy\s+or\s+wait)\b",
    re.I,
)

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


_PORTFOLIO_CUES = re.compile(
    r"\b(portfolio|holdings|inventory|my trades|my items|my stuff|"
    r"what (do )?i (own|have)|my collection|my assets|trade history)\b",
    re.I,
)

_MARKET_DEFLECTION_RE = re.compile(
    r"can'?t (provide|help|answer|give|assist|do)|"
    r"can\s?not (provide|help|answer|assist)|unable to assist|"
    r"consult (a|an|another)|dedicated source|authoritative source|"
    r"don'?t have (the )?(details|information)|outside .{0,20}scope|"
    r"refer to (a|an|another|the)|"
    r"i (don'?t|do not) know|i'?m not sure|not sure (what|if|about|how)|"
    r"no (information|data|details) (on|about|for|available)|"
    r"couldn'?t find|could not find|unable to (find|answer|help|provide)|"
    r"do(n'?t| not) have (any )?(info|information|data|details)",
    re.I,
)


_LORE_INTENT_RE = re.compile(
    r"\b(who\s+(is|are|was|were)|who'?s|tell me about|lore of|backstory|back\s?story|story of)\b",
    re.I,
)


def _names_a_frame(message: str) -> bool:
    try:
        from agents.knowledge.agent import _frames_in_query, load_alias_index

        return bool(_frames_in_query(message, load_alias_index()))
    except Exception:
        return False


def _is_pure_lore_query(message: str) -> bool:
    """True for an identity/lore question about a non-tradable subject (e.g.
    "who is Ordis"). Market would only defer these to Knowledge, so we can skip
    the Market round-trip entirely and save its tokens. Anything that names a
    tradable item or a Warframe stays on the Market-first path."""
    text = (message or "").strip()
    if not _LORE_INTENT_RE.search(text):
        return False
    normalized = re.sub(r"[^\w\s'-]", " ", text).strip()
    if find_items_in_text(normalized):
        return False
    if _names_a_frame(text):
        return False
    return True


def _should_use_knowledge_backup(message: str, market_result: dict) -> bool:
    if is_recommendation_query(message):
        return False
    # Portfolio queries always belong to market — never fall back to knowledge.
    if _PORTFOLIO_CUES.search(message):
        return False
    # The market agent decides: it calls defer_to_knowledge when a question is
    # outside trading scope (lore, abilities, quests, drops).
    if market_result.get("needs_knowledge"):
        return True
    # If Market couldn't actually answer — no response, an "I don't know", or a
    # deflection — try Knowledge before giving up, even when an item slug was
    # resolved (Market may resolve an item yet not know its lore/abilities).
    response = (market_result.get("response") or "").strip()
    if not response or _MARKET_DEFLECTION_RE.search(response):
        return True
    return False


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


def handle_query(message: str, user_id: str, session_id: str, debug: bool = False) -> dict:
    del user_id  # reserved for future auth
    usage_before = usage.total_bucket()
    guard = run_guardrails(message)
    if guard.blocked:
        logger.info("route session=%s blocked=guardrail", session_id)
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

    # Multi-agent only when message EXPLICITLY asks for both live data AND forecast/investment
    needs_multi = (
        bool(_MULTI_LIVE_RE.search(message)) and bool(_MULTI_FORECAST_RE.search(message))
    )

    if plan.agent == "forecasting" and not needs_multi:
        chart_base = os.getenv("AGENT_PUBLIC_URL") or os.getenv("BACKEND_URL")
        history = _forecast_history_for_query(session_id, conversation, resolved_message)
        try:
            result = ask_market_question(resolved_message, history=history, base_url=chart_base)
            session.save_forecast_history(session_id, result.get("history") or history)
            response = disclaimer + (result.get("answer") or "")
        except Exception as exc:
            response = (
                f"I couldn't find market data for that item. "
                f"Try being more specific — e.g. \"Saryn Prime Set\" instead of \"Saryn\". "
                f"({exc})"
            )
            result = {}
        agents_called = ["forecasting"]
        record_agent = "forecasting"

    elif needs_multi:
        # Call market for live prices/orders + forecasting for trend/investment analysis.
        # The two calls are independent, so run them concurrently to cut latency.
        chart_base = os.getenv("AGENT_PUBLIC_URL") or os.getenv("BACKEND_URL")
        live_prompt = f"Show me the current live buy/sell orders and price for: {resolved_message}"
        f_history = _forecast_history_for_query(session_id, conversation, resolved_message)
        # Market and forecasting are independent — run them concurrently. The
        # forecast call can crash on ambiguous item names, so isolate its result.
        with ThreadPoolExecutor(max_workers=2) as pool:
            market_future = pool.submit(
                market_answer, live_prompt, session_id=session_id, history=conversation
            )
            forecast_future = pool.submit(
                ask_market_question, resolved_message, history=f_history, base_url=chart_base
            )
            market_result = market_future.result()
            try:
                f_result = forecast_future.result()
                session.save_forecast_history(session_id, f_result.get("history") or f_history)
                forecast_part = (f_result.get("answer") or "").strip()
            except Exception as exc:
                f_result = {}
                forecast_part = (
                    f"Forecast unavailable: try specifying the full item name "
                    f"(e.g. \"Volt Prime Set\"). ({exc})"
                )

        market_part = (market_result.get("response") or "").strip()
        parts = []
        if market_part:
            parts.append(f"**Live Market:**\n{market_part}")
        if forecast_part:
            parts.append(f"**Forecast & Analysis:**\n{forecast_part}")
        response = disclaimer + "\n\n".join(parts)
        result = f_result
        agents_called = ["market", "forecasting"]
        if market_result.get("tier"):
            agents_called.append("ranking")
        record_agent = "forecasting"

    elif _is_pure_lore_query(message):
        # Non-tradable lore/identity — skip the Market round-trip (it would only
        # defer) and answer from Knowledge directly.
        k_history = session.get_conversation(session_id)
        k_result = enrich_response(knowledge_answer(resolved_message, history=k_history))
        result = k_result
        response = disclaimer + format_knowledge_reply(k_result)
        sources = knowledge_sources(k_result)
        agents_called = ["knowledge"]
        if k_result.get("tier"):
            agents_called.append("ranking")
        record_agent = "knowledge"

    else:
        market_result = market_answer(
            resolved_message,
            session_id=session_id,
            history=conversation,
        )
        result = market_result
        response = disclaimer + (market_result.get("response") or "")
        agents_called = ["market"]
        sources = market_sources(market_result)
        if market_result.get("tier"):
            agents_called.append("ranking")
        record_agent = "market"

        if _should_use_knowledge_backup(message, market_result):
            k_history = session.get_conversation(session_id)
            k_result = enrich_response(knowledge_answer(resolved_message, history=k_history))
            reply_text = format_knowledge_reply(k_result)
            if k_result.get("sources") or reply_text:
                result = k_result
                response = disclaimer + reply_text
                sources = knowledge_sources(k_result)
                agents_called = ["market", "knowledge"]
                if k_result.get("tier"):
                    agents_called.append("ranking")
                record_agent = "knowledge"

    outgoing = check_outgoing(response)
    response = outgoing.response
    out_flagged = guard.flagged or bool(outgoing.reason)

    item_name, item_slug = _item_from_result(result, record_agent)
    session.append_turn(
        session_id,
        message,
        response,
        agent=record_agent,
        item_name=item_name,
        item_slug=item_slug,
    )

    req_usage = usage.delta_since(usage_before)
    logger.info(
        "route session=%s agent=%s reason=%s agents=%s item=%r tokens=%d",
        session_id,
        record_agent,
        plan.reason,
        "+".join(agents_called) or "-",
        item_slug or item_name or "-",
        req_usage.get("total", 0),
    )

    out = {
        "response": response,
        "agents_called": agents_called if outgoing.ok else [],
        "guardrail_flagged": out_flagged,
        "usage": req_usage,
    }
    if outgoing.ok and plan.agent == "forecasting" and result.get("plot_url"):
        out["plot_url"] = result["plot_url"]
        names = item_names_from_result(result)
        out["chart_label"] = f"Forecast chart — {', '.join(names)}" if names else "Forecast chart"
    if outgoing.ok and sources:
        out["sources"] = sources
    if debug:
        out["routing"] = {
            "plan_agent": plan.agent,
            "record_agent": record_agent,
            "reason": plan.reason,
            "needs_multi": needs_multi,
            "item_query": plan.item_query,
        }
    return out
