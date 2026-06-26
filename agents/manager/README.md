# Manager orchestrator

FastAPI server on `:8502` routes chat and REST calls to in-process subagents. The Streamlit UI ([`app.py`](../app.py)) is the frontend.

## Run

```bash
# Terminal 1 — Manager backend
uvicorn agents.manager.api:app --host 0.0.0.0 --port 8502

# Terminal 2 — Streamlit UI
streamlit run app.py
```

Set `BACKEND_URL=http://localhost:8502` in `.env`.

## Routing

| Intent | Agent |
|--------|-------|
| Live orders / prices / portfolio | Market (default when WFM has the item) |
| WFM search miss | Knowledge + `enrich_response` |
| Price stats / forecasts / trends | Forecasting |
| Ambiguous | Light LLM classifier (`MANAGER_CHAT_MODEL`) |

Market agent includes a `lookup_tier` tool for Overframe tiers on tradable items.

## Key endpoints

See [`app.py`](../app.py) for the full HTTP contract: `/health`, `/query`, `/search`, `/item/{slug}`, `/orders/{slug}`, `/portfolio`, chart static files at `/charts/`.
