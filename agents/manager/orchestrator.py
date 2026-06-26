"""Main query orchestration pipeline."""
from __future__ import annotations

from agents.forecasting import ask_market_question
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
        result = ask_market_question(message)
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
    if sources:
        out["sources"] = sources
    return out
