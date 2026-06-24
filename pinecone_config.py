"""Pinecone and OpenAI config for vector indexing."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
_PLACEHOLDERS = ("sk-...", "pcsk_...", "your-existing-index-name", "")


def _clean_env(value: str) -> str:
    return value.strip().strip("'").strip('"')


def get_config(*, require_api_keys: bool = True) -> dict:
    load_dotenv(PROJECT_ROOT / ".env")
    cfg = {
        "openai_key": _clean_env(os.getenv("OPENAI_API_KEY", "")),
        "pinecone_key": _clean_env(os.getenv("PINECONE_API_KEY", "")),
        "index_name": _clean_env(os.getenv("PINECONE_INDEX", "")),
        "namespace": _clean_env(os.getenv("PINECONE_NAMESPACE", "warframe-items")),
        "embed_model": os.getenv("EMBED_MODEL", "text-embedding-3-small"),
        "dimensions": int(os.getenv("EMBED_DIMENSIONS", "1536")),
        "batch_size": int(os.getenv("BATCH_SIZE", "100")),
    }

    if require_api_keys:
        missing = [
            name
            for name, value in (
                ("OPENAI_API_KEY", cfg["openai_key"]),
                ("PINECONE_API_KEY", cfg["pinecone_key"]),
                ("PINECONE_INDEX", cfg["index_name"]),
            )
            if value.strip() in _PLACEHOLDERS
        ]
        if missing:
            print(
                "Missing/placeholder values in .env for: "
                + ", ".join(missing)
                + "\nCopy .env.example to .env and fill in your keys."
            )
            sys.exit(1)

    return cfg
