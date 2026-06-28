"""Session history for knowledge path and coordinated clears."""
from __future__ import annotations

_histories: dict[str, list[dict[str, str]]] = {}
_forecast_histories: dict[str, list[dict[str, str]]] = {}


def get_history(session_id: str) -> list[dict[str, str]]:
    return list(_histories.get(session_id) or [])


def save_history(session_id: str, history: list[dict[str, str]]) -> None:
    _histories[session_id] = list(history)


def get_forecast_history(session_id: str) -> list[dict[str, str]]:
    return list(_forecast_histories.get(session_id) or [])


def save_forecast_history(session_id: str, history: list[dict[str, str]]) -> None:
    _forecast_histories[session_id] = list(history)


def clear_session(session_id: str) -> None:
    _histories.pop(session_id, None)
    _forecast_histories.pop(session_id, None)
    from agents.market.agent import clear_session as clear_market_session

    clear_market_session(session_id)
