"""Agent runtime settings (OpenAI chat + Pinecone retrieval)."""
from __future__ import annotations

import os

from config.pinecone import get_pinecone_config


def get_agent_config(*, require_api_keys: bool = True) -> dict:
    cfg = get_pinecone_config(require_api_keys=require_api_keys)
    cfg.update(
        {
            "chat_model": os.getenv("CHAT_MODEL", "gpt-4o-mini"),
            "top_k": int(os.getenv("TOP_K", "5")),
            "max_history": int(os.getenv("MAX_HISTORY", "20")),
            "temperature": float(os.getenv("TEMPERATURE", "0.3")),
        }
    )
    return cfg
