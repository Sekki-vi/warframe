# Warframe Agents

Library agents for a future Ordis-style manager:

| Agent | Source | Purpose |
|-------|--------|---------|
| Knowledge | Pinecone + local alias index | Non-tradable item descriptions, stats, drops |
| Ranking | `data/tier_lists/overframe.json` | Overframe tier lookup (S–D) |
| Forecasting | Warframe Market statistics | Price forecasts, item comparison, LLM Q&A |

Knowledge does **not** embed tier data. Ranking is a separate JSON lookup the manager will call later.

## Setup

1. `pip install -r requirements.txt`
2. Copy `.env.example` → `.env` and fill in API keys
3. Processed knowledge data is in git under `data/processed/` (index + corpus). Build or refresh `data/cache/` locally (wfi lookup, wiki drops, etc.; not in git).
4. Pinecone index `warframe`, namespace `warframe` must already be populated

### Pinecone

- Index: `warframe` (1536-dim, cosine)
- Namespace: `warframe`

## Usage

### Knowledge + ranking

```python
from agents.knowledge.agent import answer, retrieve
from agents.ranking.agent import lookup_tier, enrich_response

hits, intent = retrieve("Excalibur")
print(hits[0]["name"])

result = answer("Tell me about Excalibur")
print(result["reply"])

print(lookup_tier("wisp", "warframes"))
```

### Forecasting

```python
from dotenv import load_dotenv
load_dotenv()

from agents.forecasting import forecast_item, compare_items, ask_market_question

result = forecast_item("Mag Prime Set")
print(result["stats"]["mean_end"], result["plot_url"])

comparison = compare_items(["Mag Prime Set", "Rhino Prime Set"])
print(comparison["comparison"]["cheapest_last"]["item"]["item_name"])

answer = ask_market_question("What is the median price trend for Mag Prime Set?")
print(answer["answer"])
```

**Skills:** `forecast_item`, `compare_items`, `ask_market_question` (requires `OPENAI_API_KEY`).

Chart PNGs are saved under `agents/forecasting/charts/`. Set `AGENT_PUBLIC_URL` if a manager will serve them over HTTP.

### Walk-forward backtesting

```bash
python scripts/backtest.py "Mag Prime Set"
python scripts/backtest.py --items-file backtest_items.example.txt --json-out report.json
```

## Layout

```
agents/
  knowledge/       # Pinecone Q&A
  ranking/         # Overframe tier lookup
  forecasting/     # Monte Carlo price forecasts + LLM Q&A
scripts/
  backtest.py      # Forecast evaluation CLI
```

## Tier data

Edit `data/tier_lists/overframe.json` or see [data/tier_lists/README.md](data/tier_lists/README.md).

## Future work

See [docs/ARCHITECTURE_FUTURE.md](docs/ARCHITECTURE_FUTURE.md) for the planned manager router and market agent.

## Notes

- Forecasts are probabilistic estimates based on recent market history, not trading advice.
