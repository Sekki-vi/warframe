"""Paths and constants for Warframe knowledge + ranking agents."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

_DEFAULT_DATA_DIR = (
    "/Users/kenyonjones/Documents/Things that were on my desktop/"
    "PyCharm/Data Science/Warframe Data"
)

# Optional local CSV for tradable slug fallback (see tradable_registry.py)
DATA_ROOT = Path(os.getenv("ORDERS_DATA_DIR", _DEFAULT_DATA_DIR))
ITEMS_CSV = DATA_ROOT / "warframe_items.csv"

CACHE_DIR = PROJECT_ROOT / "data" / "cache"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

WFI_ALL_JSON = CACHE_DIR / "wfi_all.json"
WFI_LOOKUP_JSON = CACHE_DIR / "wfi_lookup.json"
WFM_ITEMS_JSON = CACHE_DIR / "wfm_items.json"
WFM_SETS_JSON = CACHE_DIR / "wfm_prime_sets.json"
ALIAS_INDEX_JSON = PROCESSED_DIR / "alias_index.json"

WFM_API_BASE = "https://api.warframe.market/v2"
WFM_ASSET_BASE = "https://warframe.market/static/assets/"
WFI_ALL_URL = "https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/All.json"
WFI_CDN_BASE = "https://cdn.warframestat.us/img/"

WFM_HEADERS = {
    "accept": "application/json",
    "language": "en",
    "platform": "pc",
}
