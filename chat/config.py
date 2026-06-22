"""Chat configuration for the Warframe Market RAG chatbot."""
from __future__ import annotations

import os

from pinecone_config import get_config as get_pinecone_config


def get_chat_config(*, require_api_keys: bool = True) -> dict:
    cfg = get_pinecone_config(require_api_keys=require_api_keys)
    cfg.update(
        {
            "chat_model": os.getenv("CHAT_MODEL", "gpt-4o-mini"),
            "top_k": int(os.getenv("TOP_K", "5")),
            "flask_port": int(os.getenv("FLASK_PORT", "5000")),
            "flask_secret_key": os.getenv("FLASK_SECRET_KEY", "dev-warframe-market-secret"),
            "max_history": int(os.getenv("MAX_HISTORY", "20")),
            "temperature": float(os.getenv("TEMPERATURE", "0.3")),
        }
    )
    return cfg
