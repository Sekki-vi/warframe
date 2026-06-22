# Warframe Market RAG

RAG chatbot for Warframe Market — item descriptions, stats, and historical price aggregates from a May 30 order scrape, enriched with [Warframe Market v2](https://api.warframe.market/v2/) and [WFCD/warframe-items](https://github.com/WFCD/warframe-items).

Includes a Flask UI with Ordis-style Cephalon persona (`python3 app.py`).

## Collaborator setup

1. **Clone the repo**
   ```bash
   git clone <repo-url>
   cd warframe
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   ```
   Fill in `OPENAI_API_KEY` and `PINECONE_API_KEY`. Share keys outside git (Slack, 1Password, etc.) or use your own accounts.

4. **Optional — orders CSV path** (only for data pipeline / orders DB)
   Set `ORDERS_DATA_DIR` in `.env` to the folder containing `warframe_all_orders_raw.csv`.

5. **Run the chat UI**
   ```bash
   python3 app.py
   ```
   Open `http://127.0.0.1:5001` (port 5000 is often blocked on macOS by AirPlay Receiver).

6. **Optional — rebuild data locally**
   ```bash
   python3 build_pipeline.py --skip-fetch   # from cache (no API calls)
   python3 build_pipeline.py                # full WFM enrichment (~25 min)
   python3 build_orders_db.py               # SQLite seller lookup DB
   python3 upsert_pinecone.py               # re-index to Pinecone
   ```

### Adding collaborators on GitHub

Repo owner: **Settings → Collaborators → Add people** (by GitHub username).

Each collaborator needs:
- Accepted GitHub invite
- Their own `.env` (from `.env.example`)
- Access to the shared Pinecone index `warframe` / namespace `warframe-market`, or their own index after re-upserting

## Generated outputs (not in git)

Large files are gitignored; rebuild locally or use the shared Pinecone index.

| File | Description |
|------|-------------|
| `data/processed/order_aggregates.json` | Price stats per `(slug, rank, subtype)` |
| `data/processed/rag_documents.jsonl` | Merged RAG documents (~8.5k groups) |
| `data/processed/orders.db` | SQLite order/seller lookup |
| `data/processed/sample_documents.json` | Small examples (committed) |

## Data sources

- **Orders:** `warframe_all_orders_raw.csv` (959k rows, snapshot 2026-05-30)
- **WFM v2:** `GET /v2/items` + `GET /v2/item/{slug}` + `GET /v2/item/{slug}/set`
- **WFI:** `All.json` from GitHub, joined via `gameRef` = `uniqueName`

## Note on WFM descriptions

The bulk `/v2/items` endpoint only includes names and icons. Run `python3 build_pipeline.py` (without `--skip-fetch`) once to pull full descriptions from `/v2/item/{slug}` for all slugs.
