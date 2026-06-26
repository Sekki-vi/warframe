"""Main query orchestration pipeline."""
from __future__ import annotations

import os

from agents.forecasting.ask_agent import ask_market_question, item_names_from_result
from agents.knowledge.agent import answer as knowledge_answer
from agents.manager.guardrails import run_guardrails
from agents.manager.responses import format_knowledge_reply, knowledge_sources
from agents.manager.router import classify
from agents.manager import session
from agents.market import answer as market_answer
from agents.ranking.enrich import enrich_response


def handle_query(message: str, user_id: str, session_id: str) -> dict:
    del user_id  # reserved for future auth
    guard = run_guardrails(message)
    if guard.blocked:
        return {
            "response": guard.message,
            "agents_called": [],
            "guardrail_flagged": True,
        }

    plan = classify(message)
    agents_called: list[str] = []
    response = ""
    sources: list[dict] = []
    disclaimer = (
        "Note: market forecasts are probabilistic estimates, not guaranteed trading advice.\n\n"
        if guard.flagged
        else ""
    )

    if plan.agent == "forecasting":
        chart_base = os.getenv("AGENT_PUBLIC_URL") or os.getenv("BACKEND_URL")
        result = ask_market_question(message, base_url=chart_base)
        response = disclaimer + (result.get("answer") or "")
        agents_called = ["forecasting"]

    elif plan.agent == "market":
        result = market_answer(message, session_id=session_id)
        response = disclaimer + (result.get("response") or "")
        agents_called = ["market"]
        if result.get("tier"):
            agents_called.append("ranking")

    else:
        history = session.get_history(session_id)
        result = knowledge_answer(message, history=history)
        result = enrich_response(result)
        session.save_history(session_id, result.get("history") or history)
        response = disclaimer + format_knowledge_reply(result)
        sources = knowledge_sources(result)
        agents_called = ["knowledge"]
        if result.get("tier"):
            agents_called.append("ranking")

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
