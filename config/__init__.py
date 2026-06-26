"""Project configuration: paths, env, and agent settings."""
from config.agent import get_agent_config
from config.paths import (
    CACHE_DIR,
    DATA_ROOT,
    ITEMS_CSV,
    KNOWLEDGE_CORPUS_JSONL,
    KNOWLEDGE_INDEX_JSON,
    PROCESSED_DIR,
    PROJECT_ROOT,
    WFI_ALL_JSON,
    WFI_ALL_URL,
    WFI_CDN_BASE,
    WFI_LOOKUP_JSON,
    WFM_API_BASE,
    WFM_ASSET_BASE,
    WFM_HEADERS,
    WFM_ITEMS_JSON,
    WFM_SETS_JSON,
)
from config.pinecone import get_pinecone_config

__all__ = [
    "CACHE_DIR",
    "DATA_ROOT",
    "ITEMS_CSV",
    "KNOWLEDGE_CORPUS_JSONL",
    "KNOWLEDGE_INDEX_JSON",
    "PROCESSED_DIR",
    "PROJECT_ROOT",
    "WFI_ALL_JSON",
    "WFI_ALL_URL",
    "WFI_CDN_BASE",
    "WFI_LOOKUP_JSON",
    "WFM_API_BASE",
    "WFM_ASSET_BASE",
    "WFM_HEADERS",
    "WFM_ITEMS_JSON",
    "WFM_SETS_JSON",
    "get_agent_config",
    "get_pinecone_config",
]
