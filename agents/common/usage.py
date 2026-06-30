"""Process-wide token usage tracker for every LLM call.

Each subagent records the `usage` from its OpenAI responses here so the manager
can report per-request and cumulative token consumption (and rough cost). Thread
safe: the multi-agent path records from worker threads concurrently.
"""
from __future__ import annotations

import copy
import threading
from typing import Any

_lock = threading.Lock()


def _bucket() -> dict[str, int]:
    return {"prompt": 0, "completion": 0, "total": 0, "calls": 0}


_state: dict[str, Any] = {
    "total": _bucket(),
    "by_agent": {},
    "by_model": {},
}


def _coerce(usage: Any, *names: str) -> int:
    for name in names:
        val = getattr(usage, name, None)
        if val is None and isinstance(usage, dict):
            val = usage.get(name)
        if val:
            return int(val)
    return 0


def record(model: str, usage: Any, *, agent: str = "unknown") -> None:
    """Record token usage from an OpenAI `response.usage` object (or dict).

    Safe to call with `None` (e.g. when a response carried no usage) — it is a
    no-op. Embedding responses (no completion tokens) are handled too.
    """
    if usage is None:
        return
    prompt = _coerce(usage, "prompt_tokens", "input_tokens")
    completion = _coerce(usage, "completion_tokens", "output_tokens")
    total = _coerce(usage, "total_tokens") or (prompt + completion)
    model = model or "unknown"
    agent = agent or "unknown"

    with _lock:
        for d in (
            _state["total"],
            _state["by_agent"].setdefault(agent, _bucket()),
            _state["by_model"].setdefault(model, _bucket()),
        ):
            d["prompt"] += prompt
            d["completion"] += completion
            d["total"] += total
            d["calls"] += 1


def record_response(response: Any, *, model: str = "", agent: str = "unknown") -> None:
    """Convenience wrapper that pulls `.usage` off an OpenAI response object."""
    record(model or getattr(response, "model", "") or "", getattr(response, "usage", None), agent=agent)


def snapshot() -> dict[str, Any]:
    """Return a deep copy of the cumulative usage state."""
    with _lock:
        return copy.deepcopy(_state)


def total_bucket() -> dict[str, int]:
    """Return a copy of just the cumulative total bucket."""
    with _lock:
        return dict(_state["total"])


def delta_since(before: dict[str, int]) -> dict[str, int]:
    """Compute usage accumulated since a previously captured total bucket."""
    after = total_bucket()
    return {
        "prompt": after["prompt"] - before.get("prompt", 0),
        "completion": after["completion"] - before.get("completion", 0),
        "total": after["total"] - before.get("total", 0),
        "calls": after["calls"] - before.get("calls", 0),
    }


def reset() -> None:
    with _lock:
        _state["total"] = _bucket()
        _state["by_agent"].clear()
        _state["by_model"].clear()
