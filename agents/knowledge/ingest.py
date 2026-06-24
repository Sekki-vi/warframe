"""Get Items: WFI -> knowledge documents + alias index."""
from __future__ import annotations

import json
from collections import Counter
from typing import Any

from agents.knowledge.alias_index import build_alias_index, save_alias_index
from agents.knowledge.taxonomy import derive_taxonomy
from agents.knowledge.text_builders import build_metadata_text, build_text_for_embedding, effect_keyword_list
from agents.knowledge.tier_lists import lookup_tier
from agents.knowledge.tradable_registry import (
    build_tradable_registry,
    resolve_tradable_wfm_slug,
    should_include_wfi_doc,
)
from agents.knowledge.variants import derive_item_variant
from agents.knowledge.wiki import component_display_name, compute_wiki_url
from config import WFI_CDN_BASE, WFI_RAG_DOCS_JSONL
from wfi_lookup import load_or_build_lookup, slugify
from wfm_catalog import WFM_DETAILS_JSON, fetch_items_manifest


def _load_wfm_for_wiki(*, force_wfm: bool = False) -> dict[str, dict[str, Any]]:
    """WFM bulk manifest merged with cached /item/{slug} details (wikiLink lives there)."""
    wfm_by_slug = fetch_items_manifest(force=force_wfm)
    if WFM_DETAILS_JSON.exists():
        details = json.loads(WFM_DETAILS_JSON.read_text(encoding="utf-8"))
        for slug, detail in details.items():
            if not detail.get("wikiLink"):
                continue
            wfm_by_slug[slug] = {**wfm_by_slug.get(slug, {}), **detail}
    return wfm_by_slug


def _build_wfm_wiki_maps(
    wfm_by_slug: dict[str, dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    """name_slug -> wfm_slug, wfi_slug -> wfm_slug."""
    name_to_wfm: dict[str, str] = {}
    wfi_to_wfm: dict[str, str] = {}
    for slug, item in wfm_by_slug.items():
        wfi_to_wfm[slug] = slug
        name = item.get("name")
        if name:
            name_to_wfm[slugify(name)] = slug
    return name_to_wfm, wfi_to_wfm


def _resolve_wfm_slug(
    wfi_slug: str,
    wfi: dict[str, Any],
    name_to_wfm: dict[str, str],
    wfi_to_wfm: dict[str, str],
) -> str | None:
    if wfi_slug in wfi_to_wfm:
        return wfi_to_wfm[wfi_slug]
    name = wfi.get("name") or ""
    if name:
        key = slugify(name)
        if key in name_to_wfm:
            return name_to_wfm[key]
    return None


def _resolve_wiki_link(
    wfi_slug: str,
    wfi: dict[str, Any],
    wfm_by_slug: dict[str, dict[str, Any]],
    name_to_wfm: dict[str, str],
    wfi_to_wfm: dict[str, str],
) -> str:
    wfm_slug = _resolve_wfm_slug(wfi_slug, wfi, name_to_wfm, wfi_to_wfm)
    if not wfm_slug:
        return ""
    item = wfm_by_slug.get(wfm_slug) or {}
    return item.get("wikiLink") or ""


def build_document(
    slug: str,
    wfi: dict[str, Any],
    *,
    wfm_slug: str = "",
) -> dict[str, Any]:
    category = wfi.get("category") or ""
    item_type = wfi.get("type") or ""
    equipment_class, weapon_subtype, taxonomy = derive_taxonomy(category, item_type)

    image_url = ""
    if wfi.get("imageName"):
        image_url = WFI_CDN_BASE + wfi["imageName"]

    raw_name = wfi.get("name") or slug
    name = component_display_name(slug, raw_name, equipment_class)
    aliases = slugify(name)
    effects = effect_keyword_list(wfi)
    tier = ""
    if equipment_class in ("primary", "secondary", "melee", "archgun", "archmelee", "warframes"):
        tier = lookup_tier(slug, equipment_class)

    item_variant = derive_item_variant(slug, equipment_class)

    return {
        "id": slug,
        "slug": slug,
        "name": name,
        "description": (wfi.get("description") or "").strip(),
        "unique_name": wfi.get("uniqueName") or "",
        "category": category,
        "type": item_type,
        "equipment_class": equipment_class,
        "weapon_subtype": weapon_subtype,
        "taxonomy": taxonomy,
        "tradable": True,
        "wfm_slug": wfm_slug,
        "rarity": wfi.get("rarity") or "",
        "polarity": wfi.get("polarity") or "",
        "image_url": image_url,
        "wiki_link": compute_wiki_url(name, item_variant, equipment_class),
        "tier": tier,
        "item_variant": item_variant,
        "aliases": aliases,
        "effect_keywords": effects,
        "text_for_embedding": build_text_for_embedding(slug, wfi),
        "metadata_text": build_metadata_text(slug, wfi),
    }


def build_documents(*, force_wfm: bool = False) -> list[dict[str, Any]]:
    lookup = load_or_build_lookup()
    wfm_by_slug = _load_wfm_for_wiki(force_wfm=force_wfm)
    registry = build_tradable_registry(wfm_by_slug)
    tradable_slugs = set(registry["slugs"])
    name_to_wfm, wfi_to_wfm = _build_wfm_wiki_maps(wfm_by_slug)

    docs: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()

    for slug, wfi in lookup["by_slug"].items():
        category = wfi.get("category") or ""
        item_type = wfi.get("type") or ""
        equipment_class, _, _ = derive_taxonomy(category, item_type)
        item_variant = derive_item_variant(slug, equipment_class)

        include, reason = should_include_wfi_doc(
            slug,
            wfi,
            equipment_class=equipment_class,
            item_variant=item_variant,
            tradable_slugs=tradable_slugs,
            name_to_wfm=name_to_wfm,
            wfi_to_wfm=wfi_to_wfm,
        )
        if not include:
            excluded[reason] += 1
            continue

        wfm_slug = resolve_tradable_wfm_slug(
            slug, wfi, tradable_slugs, name_to_wfm, wfi_to_wfm
        ) or ""
        docs.append(build_document(slug, wfi, wfm_slug=wfm_slug))

    print(f"Excluded: {dict(excluded)}")
    return docs


def save_documents(docs: list[dict[str, Any]]) -> None:
    WFI_RAG_DOCS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with WFI_RAG_DOCS_JSONL.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
    print(f"Saved {len(docs)} knowledge documents -> {WFI_RAG_DOCS_JSONL}")


def run_ingest(*, force_wfm: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    docs = build_documents(force_wfm=force_wfm)
    save_documents(docs)
    index = build_alias_index(docs)
    save_alias_index(index)
    with_wiki = sum(1 for d in docs if d.get("wiki_link"))
    with_tier = sum(1 for d in docs if d.get("tier"))
    print(f"Wiki links mapped: {with_wiki}/{len(docs)}")
    print(f"Tier labels mapped: {with_tier}/{len(docs)}")
    return docs, index
