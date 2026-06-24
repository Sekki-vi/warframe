"""Paths and constants for the Warframe Market RAG pipeline."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

_DEFAULT_ORDERS_DIR = (
    "/Users/kenyonjones/Documents/Things that were on my desktop/"
    "PyCharm/Data Science/Warframe Data"
)

# Source data — set ORDERS_DATA_DIR in .env to your local CSV folder
DATA_ROOT = Path(os.getenv("ORDERS_DATA_DIR", _DEFAULT_ORDERS_DIR))
ORDERS_CSV = DATA_ROOT / "warframe_all_orders_raw.csv"
ITEMS_CSV = DATA_ROOT / "warframe_items.csv"

# Local cache and outputs
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"

WFI_ALL_JSON = CACHE_DIR / "wfi_all.json"
WFI_LOOKUP_JSON = CACHE_DIR / "wfi_lookup.json"
WFM_ITEMS_JSON = CACHE_DIR / "wfm_items.json"
WFM_SETS_JSON = CACHE_DIR / "wfm_prime_sets.json"
AGGREGATES_JSON = PROCESSED_DIR / "order_aggregates.json"
RAG_DOCS_JSON = PROCESSED_DIR / "rag_documents.json"
RAG_DOCS_JSONL = PROCESSED_DIR / "rag_documents.jsonl"
WFI_RAG_DOCS_JSONL = PROCESSED_DIR / "wfi_rag_documents.jsonl"
ALIAS_INDEX_JSON = PROCESSED_DIR / "alias_index.json"
ORDERS_DB = PROCESSED_DIR / "orders.db"

WFM_API_BASE = "https://api.warframe.market/v2"
WFM_ASSET_BASE = "https://warframe.market/static/assets/"
WFI_ALL_URL = "https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/All.json"
WFI_CDN_BASE = "https://cdn.warframestat.us/img/"

WFM_HEADERS = {
    "accept": "application/json",
    "language": "en",
    "platform": "pc",
}

CHROMA_COLLECTION = "warframe_market"
