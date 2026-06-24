# Warframe Market RAG + Live Market Agent

Ordis-style chatbot combining **warframe-items** knowledge (Pinecone RAG) with **live** warframe.market API data for prices and sellers.

## Architecture

| Layer | Source | Purpose |
|-------|--------|---------|
| Knowledge | WFCD `All.json` → Pinecone `warframe-items` | Item stats, descriptions, drops |
| Market (live) | WFM v2 API | Current orders, prices, sellers |

The orchestrator retrieves WFI knowledge for every message, then calls the **market agent** (function tools) when the operator asks about prices or sellers.

## Collaborator setup

1. **Clone** and `pip install -r requirements.txt`
2. Copy `.env.example` → `.env` and fill in API keys
3. **Build knowledge index** (first time):
   ```bash
   python3 build_wfi_docs.py --force-wfm   # tradable-only corpus (~2.5k items)
   python3 upsert_pinecone.py
   ```
4. **Run chat UI:**
   ```bash
   python3 app.py
   ```
   Open `http://127.0.0.1:5001` (port 5000 often blocked on macOS).

### Pinecone

- Index: `warframe` (1536-dim, cosine)
- Namespace: `warframe-items`

## Commands

```bash
# Build WFI-only RAG documents (tradable warframe.market items only, ~2.5k)
python3 build_wfi_docs.py
python3 build_wfi_docs.py --force-wfm   # refresh tradable slug list from WFM API

# Upsert to Pinecone (deletes stale vectors when corpus shrinks)
python3 upsert_pinecone.py

# Refresh Overframe tier lists (optional; see docs/tier_list_refresh.md)
python3 build_tier_lists.py --from-json
python3 build_wfi_docs.py

# Run Flask chat
python3 app.py
```

## Deprecated (legacy pipeline)

These scripts are kept for reference but are **not used** by the chatbot:

- `build_pipeline.py`, `merge_rag_docs.py`, `aggregate_orders.py` — old merged market+WFI docs
- `build_orders_db.py`, `orders_lookup.py` — May 30 CSV snapshot (replaced by live API)

## Market API tools

The market agent calls:

- `GET /v2/items/{slug}/orders` — live orders
- `GET /v2/orders/item/{slug}/top` — top buy/sell
- `GET /v2/items/{slug}/statistics` — price statistics

Rate limit: ~3 requests/second.

## Adding collaborators

GitHub repo → **Settings** → **Collaborators**. Share `.env` values outside git.

Each collaborator needs OpenAI + Pinecone access (shared index or re-upsert to their own).

## Tier list refresh

Weapon recommendations rank by Overframe tier data in `data/tier_lists/`. See [docs/tier_list_refresh.md](docs/tier_list_refresh.md) for weekly scrape/cron setup (`pip install -r requirements-tier.txt` for Playwright).
