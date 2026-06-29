# Manager orchestrator

FastAPI server on `:8602` routes chat and REST calls to in-process subagents. The Streamlit UI ([`app.py`](../app.py)) is the frontend.

## Run

```bash
# Terminal 1 — Manager backend
uvicorn agents.manager.api:app --host 0.0.0.0 --port 8602

# Terminal 2 — Streamlit UI
streamlit run app.py --server.port 8601
```

Set `BACKEND_URL=http://localhost:8602` and `AGENT_PUBLIC_URL=http://localhost:8602` in `.env`.

## Routing

The Manager uses an **LLM-first router** (`MANAGER_CHAT_MODEL`) enriched with routing signals: WFM item matches, keyword flags, and conversation context.

| Priority | Agent |
|----------|-------|
| Forecast / timing keywords | Forecasting |
| Portfolio / trade logging | Market |
| Everything else (incl. recommendations) | **Market first** |
| WFM miss or Market unresolved + corpus hit | **Knowledge backup** |

Flow: non-forecast queries always call **Market** first. If Market does not resolve an item (`resolved_slug` empty), the orchestrator tries **Knowledge** and uses the result only when the corpus returns source cards.

Recommendations ("recommend a good…", "best X to buy") route to Market via hard rules and LLM prompt defaults.

Ranking enriches Knowledge and Market responses via `enrich_response` / `lookup_tier`.

When Knowledge matches an item, the UI shows a structured **info card** only (no narrative LLM text). Unmatched queries return a short static not-found message.

## Session memory

All turns for a `session_id` are stored in a **unified conversation log** at the Manager layer, plus `session_meta` (`last_item`, `last_item_slug`, `last_agent`). This lets follow-ups like “how much does she cost?” resolve context from the prior turn even when routing switches agents (e.g. Knowledge → Market).

Keep the same **Session ID** in the Streamlit sidebar across messages (default `session_001`). **Clear Chat** calls `DELETE /session/{session_id}` and wipes Manager, Market, and Forecasting memory for that session.

## Key endpoints

See [`app.py`](../app.py) for the full HTTP contract: `/health`, `/query`, `/search`, `/item/{slug}`, `/orders/{slug}`, `/portfolio`, chart static files at `/charts/`.
