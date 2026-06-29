"""Input guardrails for manager /query."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from openai import OpenAI

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

# Fast keyword pass — if any hit, skip LLM scope check
_IN_SCOPE_RE = re.compile(
    r"\b("
    r"warframe|prime|blueprint|neuroptics|chassis|systems?|"
    r"platinum|plat|ducats?|credits?|trading\s+tax|"
    r"price|order|sell|buy|market|portfolio|inventory|holdings?|"
    r"forecast|invest|trend|predict|cheapest|seller|buyer|spread|"
    r"mod|riven|arcane|stance|aura|vaulted|"
    r"what\s+(i\s+)?(got|have|own|bought|purchased)|my\s+(stuff|loot|items?|collection|trades?)|"
    r"ash|volt|saryn|rhino|mesa|nova|ember|hydroid|mag|nyx|"
    r"excalibur|frost|oberon|trinity|valkyr|zephyr|banshee|"
    r"nekros|mirage|limbo|loki|chroma|vauban|titania|atlas|"
    r"ivara|inaros|octavia|harrow|khora|wisp|gara|revenant|"
    r"baruuk|gauss|hildryn|protea|xaku|lavos|yareli|sevagoth|"
    r"gyre|caliban|voruna|citrine|dagath|qorvex|dante|"
    r"what\s+(i\s+)?(got|have|own|bought)|my\s+(stuff|loot|items?|collection)"
    r")\b",
    re.I,
)

_SCOPE_CHECK_SYSTEM = """You guard a Warframe Market trading assistant. Respond with JSON only.
{"in_scope": true} if the message is about ANY of:
- Warframe game items (frames, weapons, mods, blueprints, arcanes, rivens, sets)
- Platinum prices, market orders, sellers, buyers
- The user's portfolio, inventory, purchases, trades
- Price forecasts or investment analysis for Warframe items
- Anything related to the Warframe video game market

{"in_scope": false} if the message is about:
- Real people (celebrities, politicians, historical figures)
- Unrelated topics: coding, math, sports, crypto, news, entertainment
- Requests to write poems, stories, or do tasks unrelated to Warframe trading

Be strict: when in doubt about a non-Warframe topic, return false.
Never add explanations. JSON only."""

_scope_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _scope_client
    if _scope_client is None:
        _scope_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "").strip())
    return _scope_client


def _is_in_scope(text: str) -> bool:
    """Returns True if the message is about Warframe. Fast keyword check first, LLM fallback."""
    if _IN_SCOPE_RE.search(text):
        return True
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return True  # no key → don't block
    try:
        import json
        client = _get_client()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SCOPE_CHECK_SYSTEM},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=60,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return bool(data.get("in_scope", True))
    except Exception:
        return True  # on any error → don't block


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

    if not _is_in_scope(text):
        return GuardrailResult(
            blocked=True,
            flagged=False,
            message=(
                "I'm a Warframe Market assistant — I can only help with item prices, "
                "trading orders, portfolio tracking, and price forecasts. "
                "Try asking: \"what is the price of Ash Prime Set?\" or \"show my inventory\"."
            ),
        )

    return GuardrailResult(flagged=flagged)
