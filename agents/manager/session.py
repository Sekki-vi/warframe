"""Session history for knowledge path and coordinated clears."""
from __future__ import annotations

from typing import Any

_histories: dict[str, list[dict[str, str]]] = {}


def get_history(session_id: str) -> list[dict[str, str]]:
    return list(_histories.get(session_id) or [])


def save_history(session_id: str, history: list[dict[str, str]]) -> None:
    _histories[session_id] = list(history)


def clear_session(session_id: str) -> None:
    _histories.pop(session_id, None)
    from agents.market.agent import clear_session as clear_market_session

    clear_market_session(session_id)
