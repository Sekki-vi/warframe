"""Chat service — routes knowledge and market queries."""
from __future__ import annotations

from typing import Any

from agents.knowledge.agent import answer as knowledge_answer


def chat(message: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Route chat to the Knowledge Agent (delegates market API for prices/parts/tradability)."""
    return knowledge_answer(message, history)
