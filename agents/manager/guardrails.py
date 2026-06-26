"""Input guardrails for manager /query."""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_MESSAGE_LEN = 4000

_INJECTION_PATTERNS = (
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(your\s+)?(system|prior)\s+",
    r"you\s+are\s+now\s+",
    r"jailbreak",
)

_DISCLAIMER_TRIGGERS = (
    r"\bguaranteed\s+(profit|return|win)\b",
    r"\b100%\s+(profit|return)\b",
    r"\bfinancial\s+advice\b",
)


@dataclass
class GuardrailResult:
    blocked: bool = False
    flagged: bool = False
    message: str = ""


def run_guardrails(message: str) -> GuardrailResult:
    text = (message or "").strip()
    if not text:
        return GuardrailResult(blocked=True, message="Please enter a message.")
    if len(text) > MAX_MESSAGE_LEN:
        return GuardrailResult(
            blocked=True,
            message=f"Message too long (max {MAX_MESSAGE_LEN} characters).",
        )
    lowered = text.lower()
    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            return GuardrailResult(
                blocked=True,
                flagged=True,
                message="Request blocked by safety policy.",
            )
    flagged = any(re.search(p, lowered) for p in _DISCLAIMER_TRIGGERS)
    return GuardrailResult(flagged=flagged)
