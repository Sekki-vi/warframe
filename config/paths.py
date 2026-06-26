"""Paths and constants for Warframe knowledge + ranking agents."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CACHE_DIR = PROJECT_ROOT / "data" / "cache"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

WFI_ALL_JSON = CACHE_DIR / "wfi_all.json"
WFI_LOOKUP_JSON = CACHE_DIR / "wfi_lookup.json"
KNOWLEDGE_INDEX_JSON = PROCESSED_DIR / "knowledge_index.json"
KNOWLEDGE_CORPUS_JSONL = PROCESSED_DIR / "knowledge_corpus.jsonl"

WFI_ALL_URL = "https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/All.json"
WFI_CDN_BASE = "https://cdn.warframestat.us/img/"
