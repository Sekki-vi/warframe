#!/usr/bin/env python3
"""Build Warframe Market RAG documents (no embedding/indexing by default)."""
from __future__ import annotations

import argparse
import json

from aggregate_orders import aggregate_orders
from merge_rag_docs import merge_documents, save_documents
from wfi_lookup import load_or_build_lookup
from wfm_catalog import enrich_item_details, fetch_items_manifest, fetch_prime_sets


def write_samples(docs: list[dict]) -> None:
    from config import PROCESSED_DIR

    samples = {
        "secura_dual_cestra": None,
        "creeping_bullseye": None,
        "nova_prime_set": None,
        "requiem_iv_relic": None,
    }
    for doc in docs:
        slug = doc["slug"]
        if slug in samples and samples[slug] is None:
            if slug == "creeping_bullseye" and doc.get("rank") != 5:
                continue
            if slug == "requiem_iv_relic" and doc.get("subtype") != "intact":
                continue
            samples[slug] = doc
        if all(v is not None for v in samples.values()):
            break

    out = PROCESSED_DIR / "sample_documents.json"
    out.write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Sample documents -> {out}")


def _finish(docs: list[dict], index: bool) -> None:
    save_documents(docs)
    write_samples(docs)
    wfi_hits = sum(1 for d in docs if d.get("wfi"))
    wfm_desc = sum(1 for d in docs if d.get("wfm") and d["wfm"].get("description"))
    print(f"\nCoverage: {len(docs)} docs, WFM with description {wfm_desc}, WFI {wfi_hits}")
    if index:
        from index_store import index_documents

        index_documents(docs)
    else:
        print("\nSkipping vector indexing. Run with --index when ready.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Warframe Market RAG documents")
    parser.add_argument("--force", action="store_true", help="Re-download and rebuild all caches")
    parser.add_argument("--skip-fetch", action="store_true", help="Use cached WFM/WFI only (no API calls)")
    parser.add_argument("--index", action="store_true", help="Also embed/index into Pinecone")
    parser.add_argument(
        "--build-orders-db",
        action="store_true",
        help="Import orders CSV into SQLite for seller lookup",
    )
    args = parser.parse_args()

    refresh = args.force and not args.skip_fetch
    wfi_lookup = load_or_build_lookup(force=refresh)
    wfm_by_slug = fetch_items_manifest(force=refresh)
    aggregates = aggregate_orders(force=refresh)
    slugs_needed = {a["slug"] for a in aggregates}

    prime_sets: dict = {}
    if args.skip_fetch:
        print("Skipping WFM API enrichment (--skip-fetch). Using bulk manifest + warframe-items.")
        from config import WFM_SETS_JSON

        if WFM_SETS_JSON.exists():
            prime_sets = json.loads(WFM_SETS_JSON.read_text(encoding="utf-8"))
    else:
        wfm_by_slug = enrich_item_details(slugs_needed, wfm_by_slug, force=args.force)
        prime_sets = fetch_prime_sets(wfm_by_slug, force=args.force)

    docs = merge_documents(aggregates, wfm_by_slug, wfi_lookup, prime_sets)
    _finish(docs, args.index)

    if args.build_orders_db:
        from build_orders_db import build_orders_db

        build_orders_db(force=args.force)


if __name__ == "__main__":
    main()
