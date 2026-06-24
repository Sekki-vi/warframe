#!/usr/bin/env python3
"""Regression tests for Knowledge Agent retrieval (no LLM required)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.knowledge.agent import (
    _build_context,
    _parts_hits,
    answer as knowledge_answer,
    build_sources,
    retrieve,
)
from agents.knowledge.alias_index import load_alias_index
from agents.knowledge.keyword import exact_match
from agents.knowledge.part_images import part_image_url
from config import WFI_RAG_DOCS_JSONL

REGRESSION_FILE = Path(__file__).resolve().parent / "data" / "knowledge_regression.json"

_MOCK_PARTS = [
    {
        "slug": "nova_prime_blueprint",
        "name": "Nova Prime Blueprint",
        "wfm_slug": "nova_prime_blueprint",
        "image_url": part_image_url("nova_prime_blueprint"),
        "source": "wfm_set",
    },
    {
        "slug": "nova_prime_chassis_blueprint",
        "name": "Nova Prime Chassis Blueprint",
        "wfm_slug": "nova_prime_chassis_blueprint",
        "image_url": part_image_url("nova_prime_chassis_blueprint"),
        "source": "wfm_set",
    },
]


def load_cases() -> list[dict]:
    return json.loads(REGRESSION_FILE.read_text(encoding="utf-8"))


def run_case(case: dict) -> tuple[bool, str]:
    query = case["query"]
    if case.get("skip_if_missing") and case.get("expect_doc_id"):
        idx = load_alias_index()
        if case["expect_doc_id"] not in idx["docs_by_id"]:
            return True, f"skipped (missing {case['expect_doc_id']})"
    if case.get("skip_if_no_variant"):
        idx = load_alias_index()
        variant = case["skip_if_no_variant"]
        if not idx.get("variant_to_docs", {}).get(variant):
            return True, f"skipped (no {variant} items in corpus)"

    patches = []
    if case.get("mock_parts"):
        patches.append(
            patch("agents.knowledge.agent.get_set_parts", return_value=_MOCK_PARTS)
        )

    for p in patches:
        p.start()
    try:
        hits, _intent = retrieve(query)
    finally:
        for p in reversed(patches):
            p.stop()

    messages: list[str] = []

    if case.get("expect_max_hits") is not None:
        cap = case["expect_max_hits"]
        if len(hits) > cap:
            return False, f"expected at most {cap} hits, got {len(hits)}"
        messages.append(f"max {cap} hits")

    if case.get("expect_min_hits") is not None:
        floor = case["expect_min_hits"]
        if len(hits) < floor:
            return False, f"expected at least {floor} hits, got {len(hits)}"
        messages.append(f"min {floor} hits")

    if case.get("expect_doc_id"):
        expected = case["expect_doc_id"]
        found = [h.get("doc_id") for h in hits]
        if expected not in found:
            return False, f"expected doc_id {expected!r} in {found[:5]}"
        if case.get("expect_top"):
            if hits[0].get("doc_id") != expected:
                return False, f"expected top hit {expected!r}, got {hits[0].get('doc_id')!r}"
        top_n = case.get("expect_in_top")
        if top_n is not None:
            top_ids = found[:top_n]
            if expected not in top_ids:
                return False, f"expected {expected!r} in top {top_n}, got {top_ids}"
        messages.append(f"doc_id {expected!r}")

    if case.get("expect_doc_ids_any"):
        options = case["expect_doc_ids_any"]
        found = [h.get("doc_id") for h in hits]
        matched = [d for d in options if d in found]
        if not matched:
            return False, f"expected any of {options} in {found[:5]}"
        messages.append(f"matched {matched}")

    if case.get("expect_source_all"):
        src = case["expect_source_all"]
        for h in hits:
            if h.get("source") != src:
                return False, f"expected source {src!r}, got {h.get('source')!r}"
        messages.append(f"source {src!r}")

    if case.get("expect_all_have_image"):
        for h in hits:
            if not h.get("image_url"):
                return False, f"expected image_url on {h.get('name')}"
        messages.append("all have image_url")

    if case.get("expect_taxonomy_all"):
        tax = case["expect_taxonomy_all"]
        for h in hits:
            if h.get("taxonomy") != tax:
                return False, f"expected all taxonomy {tax!r}, got {h.get('taxonomy')!r} in {h.get('name')}"
        messages.append(f"taxonomy {tax!r}")

    if case.get("expect_taxonomy_any"):
        taxes = set(case["expect_taxonomy_any"])
        found = {h.get("taxonomy") for h in hits}
        if not found & taxes:
            return False, f"expected any of {taxes}, got {found}"
        messages.append(f"taxonomies {found & taxes}")

    if case.get("expect_variant_all"):
        variant = case["expect_variant_all"]
        for h in hits:
            got = h.get("item_variant") or "base"
            if got != variant:
                return False, f"expected variant {variant!r}, got {got!r} for {h.get('name')}"
        messages.append(f"variant {variant!r}")

    if case.get("expect_tier_all"):
        tier = case["expect_tier_all"].upper()
        for h in hits:
            if (h.get("tier") or "").upper() != tier:
                return False, f"expected tier {tier!r}, got {h.get('tier')!r} for {h.get('name')}"
        messages.append(f"tier {tier!r}")

    if case.get("expect_equipment_class_all"):
        ec = case["expect_equipment_class_all"]
        for h in hits:
            if h.get("equipment_class") != ec:
                return False, f"expected equipment_class {ec!r}, got {h.get('equipment_class')!r}"
        messages.append(f"equipment_class {ec!r}")

    if case.get("expect_no_mods"):
        for h in hits:
            if h.get("equipment_class") == "mods":
                return False, f"mod hit not allowed: {h.get('name')}"
        messages.append("no mods")

    if case.get("expect_exact"):
        hit = exact_match(query)
        if not hit:
            return False, "exact match failed"
        messages.append(f"exact: {hit.get('doc_id')}")

    if not messages:
        return True, "no assertion"
    return True, ", ".join(messages)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run knowledge retrieval regression tests")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    cases = load_cases()
    passed = 0
    failed = 0

    for case in cases:
        ok, msg = run_case(case)
        label = case.get("id") or case["query"]
        if ok:
            passed += 1
            if args.verbose:
                print(f"PASS  {label}: {msg}")
        else:
            failed += 1
            print(f"FAIL  {label}: {msg}")

    print(f"\n{passed}/{len(cases)} passed, {failed} failed")

    sample_hits, _ = retrieve("recommend a shotgun")
    if sample_hits:
        for src in build_sources(sample_hits):
            if src.get("description"):
                print("FAIL  empty-ui-desc: source description should be empty")
                failed += 1
                break
            if "tradable" in src:
                print("FAIL  no-tradable-sources: tradable should not be in source cards")
                failed += 1
                break
        else:
            passed += 1
            if args.verbose:
                print("PASS  empty-ui-desc: sources have empty description")

    ctx = _build_context([{"name": "Ash Prime", "tier": "A", "text": "stats"}])
    if "listed on warframe.market" in ctx or "not listed" in ctx:
        print("FAIL  no-listing-context: context should not include market listing status")
        failed += 1
    else:
        passed += 1
        if args.verbose:
            print("PASS  no-listing-context: context has no listing status")

    idx = load_alias_index()
    bad_ec = {"skins", "glyphs", "sigils"}
    bad = [d for d in idx["docs_by_id"].values() if d.get("equipment_class") in bad_ec]
    if bad:
        print(f"FAIL  tradable-corpus: found {len(bad)} excluded equipment_class docs")
        failed += 1
    else:
        passed += 1
        if args.verbose:
            print("PASS  tradable-corpus: no skins/glyphs in alias index")

    cedo = idx["docs_by_id"].get("cedo_prime") or {}
    if cedo.get("tier") != "S":
        print(f"FAIL  cedo-prime-tier: expected tier S, got {cedo.get('tier')!r}")
        failed += 1
    else:
        passed += 1
        if args.verbose:
            print("PASS  cedo-prime-tier: tier S on cedo_prime doc")

    if WFI_RAG_DOCS_JSONL.exists():
        bad_text = 0
        with WFI_RAG_DOCS_JSONL.open(encoding="utf-8") as f:
            for line in f:
                doc = json.loads(line)
                meta = doc.get("metadata_text") or ""
                if "Not tradable on market" in meta or "Status: vaulted" in meta:
                    bad_text += 1
        if bad_text:
            print(f"FAIL  no-wfi-status: {bad_text} docs still have WFI status/tradable text")
            failed += 1
        else:
            passed += 1
            if args.verbose:
                print("PASS  no-wfi-status: no WFI tradable/vaulted lines in metadata_text")

    with patch(
        "agents.knowledge.agent.run_orders_query",
        return_value={"reply": "Primed Flow sells for 100p on warframe.market.", "sources": []},
    ):
        price = knowledge_answer("how much is Primed Flow")
    if price.get("sources"):
        print("FAIL  price-routing: expected no sources on price query")
        failed += 1
    elif "primed flow" not in (price.get("reply") or "").lower():
        print("FAIL  price-routing: reply should come from market agent")
        failed += 1
    else:
        passed += 1
        if args.verbose:
            print("PASS  price-routing: market agent handles price query")

    with patch("agents.knowledge.agent.get_set_parts", return_value=_MOCK_PARTS):
        hits, _ = _parts_hits("parts to build nova prime", {})
    if not hits or hits[0].get("name") != "Nova Prime Blueprint":
        print(f"FAIL  parts-wfm-names: expected WFM names, got {[h.get('name') for h in hits]}")
        failed += 1
    else:
        passed += 1
        if args.verbose:
            print("PASS  parts-wfm-names: part cards use WFM display names")

    with patch("agents.knowledge.agent.get_set_parts", return_value=_MOCK_PARTS):
        hits, _ = _parts_hits("parts to build nova prime", {})
    sources = build_sources(hits)
    wiki_links = [s.get("wiki_link") for s in sources if s.get("wiki_link")]
    if len(wiki_links) != 1 or wiki_links[0] != "https://wiki.warframe.com/w/Nova_Prime":
        print(f"FAIL  parts-parent-wiki: expected one parent wiki link, got {wiki_links}")
        failed += 1
    else:
        passed += 1
        if args.verbose:
            print("PASS  parts-parent-wiki: single parent wiki on first part card")

    _MOCK_CEDO_PARTS = [
        {
            "slug": "cedo_prime_blueprint",
            "name": "Cedo Prime Blueprint",
            "wfm_slug": "cedo_prime_blueprint",
            "image_url": part_image_url("cedo_prime_blueprint"),
            "source": "wfm_set",
        },
        {
            "slug": "cedo_prime_barrel",
            "name": "Cedo Prime Barrel",
            "wfm_slug": "cedo_prime_barrel",
            "image_url": part_image_url("cedo_prime_barrel"),
            "source": "wfm_set",
        },
    ]
    with patch("agents.knowledge.agent.get_set_parts", return_value=_MOCK_CEDO_PARTS):
        hits, _ = _parts_hits("parts to build cedo prime", {})
    sources = build_sources(hits)
    wiki_links = [s.get("wiki_link") for s in sources if s.get("wiki_link")]
    if len(wiki_links) != 1 or wiki_links[0] != "https://wiki.warframe.com/w/Cedo_Prime":
        print(f"FAIL  weapon-parts-parent-wiki: expected Cedo Prime wiki once, got {wiki_links}")
        failed += 1
    else:
        passed += 1
        if args.verbose:
            print("PASS  weapon-parts-parent-wiki: single parent wiki for weapon parts")

    print(f"\nFinal: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
