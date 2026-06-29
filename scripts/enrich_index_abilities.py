"""Enrich knowledge docs with Warframe ability + passive text from All.json.

The pre-built knowledge corpus/index store only base stats and a flavor
description per Warframe, so ability questions ("what does Saryn's passive do")
have nothing to ground on. This builder folds each frame's abilities and passive
(already present in the WFCD `All.json` cache) into the docs' `metadata_text` and
`text_for_embedding`.

It edits both committed artifacts in place and is idempotent (re-running it does
not duplicate the appended section):

    data/processed/knowledge_index.json   # keyword/exact path — used at runtime
    data/processed/knowledge_corpus.jsonl # source archive — for a Pinecone rebuild

The keyword path reads `docs_by_id[*].metadata_text` directly, so enriching the
index alone makes named-frame ability questions work without re-embedding. Re-run
the Pinecone build separately to also improve ability-phrased semantic recall.

Usage:
    python -m scripts.enrich_index_abilities
"""
from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

from config.paths import WFI_ALL_JSON, KNOWLEDGE_INDEX_JSON, KNOWLEDGE_CORPUS_JSONL

_MARKUP_TAG = re.compile(r"<[^>]+>")
# Stat placeholders the wiki fills with numbers we do not have (|DURATION|, |DAMAGE|…).
_STAT_TOKEN = re.compile(r"\|[^|]+\|")
_WS = re.compile(r"\s+")
_SECTION_MARKER = "Abilities:"


def _clean(text: str) -> str:
    text = _MARKUP_TAG.sub("", text or "")
    text = _STAT_TOKEN.sub("X", text)
    text = unescape(text)
    return _WS.sub(" ", text).strip()


def _ability_text(entry: dict[str, Any]) -> str:
    parts: list[str] = []
    abilities = entry.get("abilities") or []
    if abilities:
        rendered = "; ".join(
            f"{_clean(a.get('name') or '')} — {_clean(a.get('description') or '')}".strip(" —")
            for a in abilities
            if a.get("name")
        )
        if rendered:
            parts.append(f"Abilities: {rendered}.")
    passive = _clean(entry.get("passiveDescription") or "")
    if passive:
        parts.append(f"Passive: {passive}.")
    return " ".join(parts)


def _ability_index_by_uname() -> dict[str, dict[str, Any]]:
    raw = json.loads(WFI_ALL_JSON.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else list(raw.values())
    out: dict[str, dict[str, Any]] = {}
    for it in items:
        if isinstance(it, dict) and it.get("uniqueName") and it.get("abilities"):
            out[it["uniqueName"]] = it
    return out


def _append_section(doc: dict[str, Any], section: str) -> bool:
    """Append the ability section to a doc's text fields. Returns True if changed."""
    if not section:
        return False
    changed = False
    for field in ("metadata_text", "text_for_embedding"):
        current = doc.get(field) or ""
        if _SECTION_MARKER in current:
            continue  # already enriched — idempotent
        doc[field] = f"{current.rstrip()} {section}".strip()
        changed = True
    return changed


def enrich() -> dict[str, int]:
    ability_idx = _ability_index_by_uname()

    # --- knowledge_index.json (runtime keyword/exact path) ---
    index = json.loads(KNOWLEDGE_INDEX_JSON.read_text(encoding="utf-8"))
    docs = index.get("docs_by_id") or {}
    enriched = 0
    for doc in docs.values():
        if doc.get("equipment_class") != "warframes":
            continue
        entry = ability_idx.get(doc.get("unique_name"))
        if not entry:
            continue
        if _append_section(doc, _ability_text(entry)):
            enriched += 1
    KNOWLEDGE_INDEX_JSON.write_text(
        json.dumps(index, ensure_ascii=False), encoding="utf-8"
    )

    # --- knowledge_corpus.jsonl (archive for Pinecone rebuild) ---
    corpus_enriched = 0
    lines: list[str] = []
    for line in KNOWLEDGE_CORPUS_JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        doc = json.loads(line)
        if doc.get("equipment_class") == "warframes":
            entry = ability_idx.get(doc.get("unique_name"))
            if entry and _append_section(doc, _ability_text(entry)):
                corpus_enriched += 1
        lines.append(json.dumps(doc, ensure_ascii=False))
    KNOWLEDGE_CORPUS_JSONL.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"index_docs": enriched, "corpus_docs": corpus_enriched}


if __name__ == "__main__":
    stats = enrich()
    print(
        f"Enriched {stats['index_docs']} index docs and "
        f"{stats['corpus_docs']} corpus docs with abilities + passive."
    )
