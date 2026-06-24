"""Build alias + taxonomy index from knowledge documents."""
from __future__ import annotations

import json
from typing import Any

from config import ALIAS_INDEX_JSON
from wfi_lookup import slugify


def _append_index(bucket: dict[str, list[str]], key: str, doc_id: str) -> None:
    if not key:
        return
    bucket.setdefault(key, [])
    if doc_id not in bucket[key]:
        bucket[key].append(doc_id)


def build_alias_index(docs: list[dict[str, Any]]) -> dict[str, Any]:
    name_to_doc: dict[str, str] = {}
    slug_to_doc: dict[str, str] = {}
    alias_to_doc: dict[str, str] = {}
    weapon_subtype_to_docs: dict[str, list[str]] = {}
    taxonomy_to_docs: dict[str, list[str]] = {}
    equipment_class_to_docs: dict[str, list[str]] = {}
    effect_to_docs: dict[str, list[str]] = {}
    variant_to_docs: dict[str, list[str]] = {}
    docs_by_id: dict[str, dict[str, Any]] = {}

    for doc in docs:
        doc_id = doc["id"]
        docs_by_id[doc_id] = doc

        name = doc.get("name") or ""
        slug = doc.get("slug") or doc_id
        name_lower = name.lower().strip()

        if name_lower:
            name_to_doc[name_lower] = doc_id
        slug_to_doc[slug] = doc_id
        alias_to_doc[slugify(name)] = doc_id

        for alias in (doc.get("aliases") or "").split(","):
            alias = alias.strip().lower()
            if alias:
                alias_to_doc[alias] = doc_id

        ec = doc.get("equipment_class") or ""
        ws = doc.get("weapon_subtype") or ""
        tax = doc.get("taxonomy") or ""

        _append_index(equipment_class_to_docs, ec, doc_id)
        _append_index(taxonomy_to_docs, tax, doc_id)
        _append_index(weapon_subtype_to_docs, ws, doc_id)

        # Also index base weapon subtype for weapons (shotgun not shotgun_mod)
        if ec in ("primary", "secondary", "melee", "archgun", "archmelee"):
            if ws and not ws.endswith("_mod"):
                _append_index(weapon_subtype_to_docs, ws, doc_id)

        for effect in doc.get("effect_keywords") or []:
            _append_index(effect_to_docs, effect.lower(), doc_id)

        variant = doc.get("item_variant") or ""
        if variant:
            _append_index(variant_to_docs, variant, doc_id)

    return {
        "name_to_doc": name_to_doc,
        "slug_to_doc": slug_to_doc,
        "alias_to_doc": alias_to_doc,
        "weapon_subtype_to_docs": weapon_subtype_to_docs,
        "taxonomy_to_docs": taxonomy_to_docs,
        "equipment_class_to_docs": equipment_class_to_docs,
        "effect_to_docs": effect_to_docs,
        "variant_to_docs": variant_to_docs,
        "docs_by_id": docs_by_id,
    }


def save_alias_index(index: dict[str, Any]) -> None:
    ALIAS_INDEX_JSON.parent.mkdir(parents=True, exist_ok=True)
    ALIAS_INDEX_JSON.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    print(f"Saved alias index -> {ALIAS_INDEX_JSON}")


def load_alias_index() -> dict[str, Any]:
    if not ALIAS_INDEX_JSON.exists():
        raise FileNotFoundError(
            f"Alias index not found at {ALIAS_INDEX_JSON}. Run build_wfi_docs.py first."
        )
    return json.loads(ALIAS_INDEX_JSON.read_text(encoding="utf-8"))
