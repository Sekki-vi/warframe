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
    # Warframe lore, characters, factions, and places (not tradable items, but
    # still in-scope — the Knowledge agent answers these).
    r"ordis|lotus|cephalon|teshin|tenno|operator|orbiter|"
    r"grineer|corpus|infested|orokin|sentient|stalker|void|"
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
- Warframe lore, characters, factions, NPCs, quests, locations, or story
  (e.g. Ordis, the Lotus, Teshin, Cephalons, Tenno, Grineer, Corpus, the Void)
- Anything related to the Warframe video game

{"in_scope": false} if the message is about:
- Real-world people (celebrities, politicians, historical figures) — NOT Warframe characters
- Unrelated topics: coding, math, sports, crypto, news, real-world entertainment
- Requests to write poems, stories, or do tasks unrelated to Warframe

A character, faction, or place from the Warframe game is IN scope even if it is
not a tradable item. When in doubt about whether something is part of the
Warframe universe, return true; only return false for clearly off-topic requests.
Never add explanations. JSON only."""

_scope_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _scope_client
    if _scope_client is None:
        _scope_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "").strip())
    return _scope_client


_IDENTITY_INTENT_RE = re.compile(
    r"\b(who\s+(is|are|was|were)|who'?s|tell me about|lore of|backstory|back\s?story|story of)\b",
    re.I,
)


def _is_in_scope(text: str) -> bool:
    """Returns True if the message is about Warframe. Fast keyword check first, LLM fallback."""
    if _IN_SCOPE_RE.search(text):
        return True
    # Identity/lore questions ("who is X", "tell me about X") are the Knowledge
    # agent's domain. Let it judge and answer (or decline) rather than pre-blocking
    # unknown Warframe names here — the keyword list can't enumerate every name.
    if _IDENTITY_INTENT_RE.search(text):
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


_SECRET_PATTERNS = (
    r"sk-[A-Za-z0-9_-]{20,}",          # OpenAI key
    r"pcsk_[A-Za-z0-9_-]{20,}",        # Pinecone key
    r"gh[pousr]_[A-Za-z0-9]{20,}",     # GitHub token
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
)

_TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\)|File \"[^\"]+\", line \d+", re.I)

_UNGROUNDED_GUARANTEE_RE = re.compile(
    r"\b(guaranteed\s+(to\s+)?(profit|return|win|increase|decrease|rise|fall|go\s+up|go\s+down)|"
    r"100%\s+(guaranteed|profit|return|certain)|"
    r"certain(ly)?\s+(to\s+)?(profit|increase|decrease)|risk[\s-]?free)\b",
    re.I,
)

_SYSTEM_LEAK_RE = re.compile(
    r"you are a warframe market trading sub-agent|"
    r"you guard a warframe market trading assistant|"
    r"classify warframe assistant routing|"
    r"do not answer the user question",
    re.I,
)

_MAX_RESPONSE_LEN = 6000


@dataclass
class GuardrailResult:
    blocked: bool = False
    flagged: bool = False
    message: str = ""


@dataclass
class OutgoingResult:
    ok: bool = True
    response: str = ""
    reason: str = ""


def check_outgoing(response: str) -> OutgoingResult:
    """Validate/sanitize the agent's response before it reaches the user."""
    text = (response or "").strip()

    if not text:
        return OutgoingResult(
            ok=False,
            response="I wasn't able to generate a response for that. Could you rephrase?",
            reason="empty_response",
        )

    for pattern in _SECRET_PATTERNS:
        if re.search(pattern, text):
            return OutgoingResult(
                ok=False,
                response="I hit an internal error generating that response. Please try again.",
                reason="secret_leak",
            )

    if _TRACEBACK_RE.search(text):
        return OutgoingResult(
            ok=False,
            response="I hit an internal error generating that response. Please try again.",
            reason="traceback_leak",
        )

    if _SYSTEM_LEAK_RE.search(text):
        return OutgoingResult(
            ok=False,
            response="I wasn't able to generate a proper response for that. Could you rephrase?",
            reason="system_prompt_leak",
        )

    sanitized = text
    flagged_guarantee = bool(_UNGROUNDED_GUARANTEE_RE.search(text))
    if flagged_guarantee:
        sanitized = (
            "Note: market forecasts are probabilistic estimates, not guaranteed trading advice.\n\n"
            + text
        )

    if len(sanitized) > _MAX_RESPONSE_LEN:
        sanitized = sanitized[:_MAX_RESPONSE_LEN].rstrip() + "\n\n…(truncated)"

    return OutgoingResult(
        ok=True,
        response=sanitized,
        reason="guarantee_disclaimer_added" if flagged_guarantee else "",
    )


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
