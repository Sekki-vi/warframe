"""Normalize subagent outputs for Streamlit UI."""
from __future__ import annotations

from typing import Any


def format_knowledge_reply(result: dict[str, Any]) -> str:
    """Return Ordis reply text only; source cards are rendered separately from sources."""
    sources = result.get("sources") or []
    if sources:
        return ""
    return (result.get("reply") or "").strip()


def knowledge_sources(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Source cards for knowledge path (image, description, wiki, drops, tier)."""
    out: list[dict[str, Any]] = []
    for src in result.get("sources") or []:
        if not isinstance(src, dict):
            continue
        out.append({
            "name": src.get("name") or "",
            "description": src.get("description") or "",
            "tier": src.get("tier") or result.get("tier") or "",
            "image_url": src.get("image_url") or "",
            "wiki_link": src.get("wiki_link") or "",
            "drop_sources": list(src.get("drop_sources") or [])[:4],
        })
    return out


def portfolio_error_response(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") == "error":
        return {"error": result.get("message", "Unknown error")}
    return result
