"""Unified session memory for Manager orchestration."""
from __future__ import annotations

_conversations: dict[str, list[dict[str, str]]] = {}
_session_meta: dict[str, dict[str, str]] = {}
_forecast_histories: dict[str, list[dict[str, str]]] = {}

_DEFAULT_MAX_TURNS = 10


def get_conversation(session_id: str, max_turns: int = _DEFAULT_MAX_TURNS) -> list[dict[str, str]]:
    history = list(_conversations.get(session_id) or [])
    max_messages = max(1, max_turns) * 2
    if len(history) <= max_messages:
        return history
    return history[-max_messages:]


def get_history(session_id: str) -> list[dict[str, str]]:
    """Alias for Knowledge agent compatibility."""
    return get_conversation(session_id)


def save_history(session_id: str, history: list[dict[str, str]]) -> None:
    """Sync conversation from agent-returned history (role/content only)."""
    _conversations[session_id] = [
        {"role": str(h["role"]), "content": str(h["content"])}
        for h in history
        if h.get("role") in ("user", "assistant") and h.get("content") is not None
    ]


def get_session_meta(session_id: str) -> dict[str, str]:
    return dict(_session_meta.get(session_id) or {})


def append_turn(
    session_id: str,
    user: str,
    assistant: str,
    *,
    agent: str = "",
    item_name: str = "",
    item_slug: str = "",
) -> None:
    history = list(_conversations.get(session_id) or [])
    history.append({"role": "user", "content": user})
    history.append({"role": "assistant", "content": assistant})
    _conversations[session_id] = history

    meta = dict(_session_meta.get(session_id) or {})
    if agent:
        meta["last_agent"] = agent
    if item_name:
        meta["last_item"] = item_name
    if item_slug:
        meta["last_item_slug"] = item_slug
    _session_meta[session_id] = meta


def get_forecast_history(session_id: str) -> list[dict[str, str]]:
    return list(_forecast_histories.get(session_id) or [])


def save_forecast_history(session_id: str, history: list[dict[str, str]]) -> None:
    _forecast_histories[session_id] = list(history)


def clear_session(session_id: str) -> None:
    _conversations.pop(session_id, None)
    _session_meta.pop(session_id, None)
    _forecast_histories.pop(session_id, None)
    from agents.market.agent import clear_session as clear_market_session

    clear_market_session(session_id)
