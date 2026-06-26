"""Fetch and parse acquisition / drop info from the Warframe wiki."""
from __future__ import annotations

import json
import re
import time
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests

from config import CACHE_DIR

WIKI_API = "https://wiki.warframe.com/api.php"
WIKI_BASE = "https://wiki.warframe.com/w/"
CACHE_FILE = CACHE_DIR / "wiki_drops.json"
_CACHE_TTL_SEC = 7 * 24 * 3600
_MAX_SOURCES = 8
_MAX_SUMMARY_CHARS = 480

_ACQUISITION_SECTION = re.compile(
    r'id="Acquisition"[^>]*>.*?</h2>(.*?)(?=<div class="mw-heading mw-heading2">|<h2[^>]*id=|\Z)',
    re.IGNORECASE | re.DOTALL,
)
_BOILERPLATE = re.compile(
    r"all drop rates data is obtained from de's official drop tables",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_EDIT_MARKERS = re.compile(r"\[ edit \| edit source \]", re.IGNORECASE)
_TABLE_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_TABLE_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)


def wiki_page_from_url(wiki_link: str) -> str:
    """Return MediaWiki page title from a canonical wiki URL."""
    link = (wiki_link or "").strip()
    if not link.startswith(WIKI_BASE):
        return ""
    return unquote(link[len(WIKI_BASE) :]).strip("/")


def _clean_html_text(fragment: str) -> str:
    text = _TAG_RE.sub(" ", fragment)
    text = _EDIT_MARKERS.sub("", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_acquisition_html(html: str) -> list[str]:
    """Extract acquisition summary lines from parsed wiki HTML."""
    match = _ACQUISITION_SECTION.search(html or "")
    if not match:
        return []

    section = match.group(1)
    sources: list[str] = []
    seen: set[str] = set()

    def _add(line: str) -> None:
        line = line.strip(" .")
        if not line or len(line) < 4:
            return
        if _BOILERPLATE.search(line):
            return
        key = line.lower()
        if key in seen:
            return
        seen.add(key)
        sources.append(line)

    # Lead paragraph(s) before tables
    for para in re.findall(r"<p[^>]*>(.*?)</p>", section, re.IGNORECASE | re.DOTALL):
        text = _clean_html_text(para)
        if text and not text.lower().startswith("this section"):
            _add(text)
            if len(sources) >= 2:
                break

    for item in re.findall(r"<li[^>]*>(.*?)</li>", section, re.IGNORECASE | re.DOTALL):
        text = _clean_html_text(item)
        if text:
            _add(text)
            if len(sources) >= 3:
                break

    # Acquisition table: Item | Source | ...
    for row in _TABLE_ROW.findall(section):
        if "acquisition-table" not in section and "<th" in row and "Source" in row:
            continue
        cells = [_clean_html_text(c) for c in _TABLE_CELL.findall(row)]
        cells = [c for c in cells if c]
        if len(cells) >= 2 and cells[0].lower() not in ("item", "source"):
            item, source = cells[0], cells[1]
            if source and not _BOILERPLATE.search(source):
                _add(f"{item}: {source}" if item else source)

    out: list[str] = []
    for line in sources:
        if len(line) > _MAX_SUMMARY_CHARS:
            line = line[: _MAX_SUMMARY_CHARS - 1].rstrip() + "…"
        out.append(line)
        if len(out) >= _MAX_SOURCES:
            break
    return out


def _load_cache() -> dict[str, Any]:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_cache(data: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_acquisition(wiki_link: str, *, force: bool = False) -> list[str]:
    """Return acquisition lines for a wiki page (cached on disk)."""
    page = wiki_page_from_url(wiki_link)
    if not page:
        return []

    cache = _load_cache()
    entry = cache.get(page) or {}
    fetched_at = entry.get("fetched_at") or 0
    if not force and entry.get("sources") is not None and (time.time() - fetched_at) < _CACHE_TTL_SEC:
        return list(entry.get("sources") or [])

    params = {
        "action": "parse",
        "page": page,
        "prop": "text",
        "format": "json",
    }
    try:
        resp = requests.get(WIKI_API, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        html = payload.get("parse", {}).get("text", {}).get("*") or ""
        sources = parse_acquisition_html(html)
    except (requests.RequestException, json.JSONDecodeError, KeyError):
        sources = list(entry.get("sources") or [])

    cache[page] = {"fetched_at": time.time(), "sources": sources, "wiki_link": wiki_link}
    _save_cache(cache)
    return sources
