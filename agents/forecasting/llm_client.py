"""OpenAI client helpers for the forecasting subagent."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from agents.common import usage

DEFAULT_MODEL = "gpt-4.1-mini"
FALLBACK_MODEL = "gpt-4o-mini"


class LLMConfigError(RuntimeError):
    """Raised when OpenAI is not configured."""


def get_model() -> str:
    return os.environ.get("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise LLMConfigError(
            "OPENAI_API_KEY is not set. Add it to your environment before using ask/LLM features."
        )
    return OpenAI(api_key=api_key)


def _build_messages(
    system: str,
    user: str,
    history: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})
    return messages


def chat_json(
    system: str,
    user: str,
    *,
    history: list[dict[str, str]] | None = None,
    temperature: float = 0.1,
) -> dict[str, Any]:
    client = get_client()
    model = get_model()
    messages = _build_messages(system, user, history)
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=messages,
        )
    except Exception as exc:
        if model != FALLBACK_MODEL:
            response = client.chat.completions.create(
                model=FALLBACK_MODEL,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=messages,
            )
        else:
            raise RuntimeError(f"OpenAI request failed: {exc}") from exc

    usage.record_response(response, agent="forecasting")
    content = response.choices[0].message.content or "{}"
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise RuntimeError("OpenAI returned a non-object JSON response")
    return payload


def chat_text(
    system: str,
    user: str,
    *,
    history: list[dict[str, str]] | None = None,
    temperature: float = 0.3,
) -> str:
    client = get_client()
    model = get_model()
    messages = _build_messages(system, user, history)
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
        )
    except Exception as exc:
        if model != FALLBACK_MODEL:
            response = client.chat.completions.create(
                model=FALLBACK_MODEL,
                temperature=temperature,
                messages=messages,
            )
        else:
            raise RuntimeError(f"OpenAI request failed: {exc}") from exc

    usage.record_response(response, agent="forecasting")
    return (response.choices[0].message.content or "").strip()
