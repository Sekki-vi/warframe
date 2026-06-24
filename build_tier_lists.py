#!/usr/bin/env python3
"""Build or refresh Overframe tier list JSON files."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.knowledge.tier_lists import TIER_LISTS_DIR
from wfi_lookup import load_or_build_lookup, slugify

OVERFRAME_URLS = {
    "overframe_primary.json": "https://overframe.gg/tier-list/primary-weapons/",
    "overframe_secondary.json": "https://overframe.gg/tier-list/secondary-weapons/",
    "overframe_melee.json": "https://overframe.gg/tier-list/melee-weapons/",
    "overframe_warframes.json": "https://overframe.gg/tier-list/warframes/",
}

TIER_SECTIONS = ["S", "A", "B", "C", "D"]

# Slugs that should have tier entries; used by --check for gap detection.
CHECK_SLUGS = {
    "overframe_primary.json": ["cedo_prime", "arca_plasmor", "kuva_bramma"],
    "overframe_warframes.json": ["wisp", "wisp_prime", "gara_prime"],
}


def _resolve_slug(name: str, lookup: dict[str, Any]) -> str | None:
    key = slugify(name)
    if key in lookup["by_slug"]:
        return key
    for slug, wfi in lookup["by_slug"].items():
        if (wfi.get("name") or "").lower() == name.lower():
            return slug
    return None


def load_existing_tier_files() -> dict[str, dict[str, Any]]:
    """Load existing tier JSON files from data/tier_lists/."""
    merged: dict[str, dict[str, Any]] = {}
    TIER_LISTS_DIR.mkdir(parents=True, exist_ok=True)
    for path in TIER_LISTS_DIR.glob("overframe_*.json"):
        merged[path.name] = json.loads(path.read_text(encoding="utf-8"))
    return merged


def merge_seed_files() -> dict[str, dict[str, Any]]:
    return load_existing_tier_files()


def merge_tier_data(
    existing: dict[str, dict[str, Any]],
    scraped: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Union scraped entries with existing seeds (existing wins on conflict)."""
    out: dict[str, dict[str, Any]] = {}
    all_names = set(existing) | set(scraped)
    for fname in all_names:
        base = dict(scraped.get(fname) or {})
        base.update(existing.get(fname) or {})
        out[fname] = base
    return out


def scrape_overframe() -> dict[str, dict[str, Any]]:
    """Scrape Overframe tier pages with Playwright (optional dependency)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    lookup = load_or_build_lookup()
    results: dict[str, dict[str, Any]] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        for fname, url in OVERFRAME_URLS.items():
            print(f"Scraping {url} ...")
            page.goto(url, wait_until="networkidle", timeout=120_000)
            page.wait_for_timeout(3000)
            entries: dict[str, Any] = {}
            for tier in TIER_SECTIONS:
                section = page.locator(f"text={tier} Tier").first
                if not section.count():
                    continue
                container = section.locator("xpath=ancestor::section[1]")
                names = container.locator("a, [class*='weapon'], [class*='item']").all_inner_texts()
                for raw in names:
                    name = raw.strip()
                    if not name or len(name) < 2 or name.startswith("#"):
                        continue
                    slug = _resolve_slug(name, lookup)
                    if slug:
                        entries[slug] = {"tier": tier, "name": lookup["by_slug"][slug].get("name") or name}
            results[fname] = entries
            print(f"  {fname}: {len(entries)} entries")
        browser.close()
    return results


def write_tier_files(data: dict[str, dict[str, Any]], *, dry_run: bool = False) -> None:
    TIER_LISTS_DIR.mkdir(parents=True, exist_ok=True)
    for fname, entries in data.items():
        path = TIER_LISTS_DIR / fname
        if dry_run:
            print(f"Would write {len(entries)} entries -> {path}")
            continue
        path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {len(entries)} entries -> {path}")

    if not dry_run:
        stamp = TIER_LISTS_DIR / "last_updated.txt"
        stamp.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        print(f"Updated {stamp}")


def check_tier_gaps() -> int:
    """Report known S-tier slugs missing from tier JSON files."""
    data = load_existing_tier_files()
    missing = 0
    for fname, slugs in CHECK_SLUGS.items():
        entries = data.get(fname) or {}
        for slug in slugs:
            if slug not in entries:
                print(f"MISSING  {fname}: {slug}")
                missing += 1
            else:
                print(f"OK       {fname}: {slug} -> {entries[slug].get('tier')}")
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Overframe tier list JSON")
    parser.add_argument("--from-json", action="store_true", help="Reload existing seed files only")
    parser.add_argument("--scrape", action="store_true", help="Scrape overframe.gg with Playwright")
    parser.add_argument("--dry-run", action="store_true", help="Print counts without writing")
    parser.add_argument("--check", action="store_true", help="Report missing entries for known S-tier slugs")
    args = parser.parse_args()

    if args.check:
        missing = check_tier_gaps()
        raise SystemExit(1 if missing else 0)

    existing = load_existing_tier_files()

    if args.scrape:
        scraped = scrape_overframe()
        data = merge_tier_data(existing, scraped)
    else:
        data = existing
        if not data:
            print(f"No tier files in {TIER_LISTS_DIR}")
            return

    write_tier_files(data, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
