# Tier list refresh

Overframe tier data powers weapon and warframe recommendations. Refresh weekly (or after major patches).

## Validate tier seeds

```bash
python3 build_tier_lists.py --check
```

Reports missing entries for known S-tier slugs (e.g. `cedo_prime`, `wisp_prime`).

## Quick refresh

```bash
cd warframe

# Re-scrape Overframe (requires Playwright; merges with existing seeds)
pip install -r requirements-tier.txt
playwright install chromium
python3 build_tier_lists.py --scrape
python3 build_tier_lists.py --check

# Re-join tier + item_variant onto knowledge docs + alias index
# Corpus is tradable-only (CSV baseline + WFM API); use --force-wfm to refresh tradable slugs
python3 build_wfi_docs.py --force-wfm

# Re-upsert Pinecone metadata (tier, item_variant, description)
python3 upsert_pinecone.py
```

Scrape merges scraped data with existing JSON — manual seeds like `cedo_prime` are never dropped on partial scrape failures.

## Cron (Linux/macOS)

```cron
0 3 * * 0 cd /path/to/warframe && python3 build_tier_lists.py --scrape && python3 build_wfi_docs.py && python3 upsert_pinecone.py
```

## launchd (macOS)

1. Edit `scripts/com.warframe.tierlists.plist` — set `WorkingDirectory` to your warframe project path.
2. Load: `launchctl load ~/Library/LaunchAgents/com.warframe.tierlists.plist`

## Seed-only mode (no Playwright)

Hand-edit JSON in `data/tier_lists/overframe_*.json` (weapons + `overframe_warframes.json`), then:

```bash
python3 build_tier_lists.py --from-json
python3 build_wfi_docs.py
python3 upsert_pinecone.py
```
