"""Sub-agent health probes for /health."""
from __future__ import annotations

import os
from pathlib import Path

from config import PROJECT_ROOT

from agents.ranking.tier_store import OVERFRAME_JSON

VERSION = "0.1.0"


def _probe_market() -> dict:
    try:
        from agents.market.tools.wfm_api import search_item

        search_item("prime")
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "degraded", "detail": str(exc)}


def _probe_knowledge() -> dict:
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return {"status": "degraded", "detail": "OPENAI_API_KEY missing"}
    if not os.getenv("PINECONE_API_KEY", "").strip():
        return {"status": "degraded", "detail": "PINECONE_API_KEY missing"}
    index_path = PROJECT_ROOT / "data" / "processed" / "knowledge_index.json"
    if not index_path.exists():
        return {"status": "degraded", "detail": "knowledge_index.json missing"}
    return {"status": "ok"}


def _probe_forecasting() -> dict:
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return {"status": "degraded", "detail": "OPENAI_API_KEY missing"}
    return {"status": "ok"}


def _probe_ranking() -> dict:
    if OVERFRAME_JSON.exists():
        return {"status": "ok"}
    return {"status": "degraded", "detail": "overframe.json missing"}


def health_payload() -> dict:
    sub_agents = {
        "knowledge": _probe_knowledge(),
        "ranking": _probe_ranking(),
        "market": _probe_market(),
        "forecasting": _probe_forecasting(),
    }
    overall = "ok" if all(v["status"] == "ok" for v in sub_agents.values()) else "degraded"
    return {"status": overall, "version": VERSION, "sub_agents": sub_agents}
