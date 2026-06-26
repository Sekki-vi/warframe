# Warframe Market Forecast Agent

Python subagent that forecasts and compares Warframe Market item prices from completed-trade statistics. Includes optional OpenAI-powered natural-language Q&A.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
copy .env.example .env        # set OPENAI_API_KEY for ask/LLM features
```

## Python API

```python
from dotenv import load_dotenv
load_dotenv()

from agent.forecasting import forecast_item, compare_items, ask_market_question

result = forecast_item("Mag Prime Set")
print(result["stats"]["mean_end"], result["plot_url"])

comparison = compare_items(["Mag Prime Set", "Rhino Prime Set"])
print(comparison["comparison"]["cheapest_last"]["item"]["item_name"])

answer = ask_market_question("What is the median price trend for Mag Prime Set?")
print(answer["answer"])
```

## Skills

| Skill | Module | Description |
|-------|--------|-------------|
| `forecast_item` | `agent.forecasting.warframe_forecast_agent` | Forecast one item |
| `compare_items` | `agent.forecasting.warframe_forecast_agent` | Compare two or more items |
| `ask_market_question` | `agent.forecasting.ask_agent` | Natural-language Q&A (requires `OPENAI_API_KEY`) |

Chart PNGs are saved under `agent/forecasting/charts/`. Set `AGENT_PUBLIC_URL` if a manager will serve them over HTTP.

## Walk-forward backtesting

```bash
python scripts/backtest.py "Mag Prime Set"
python scripts/backtest.py --items-file backtest_items.example.txt --json-out report.json
```

## Layout

```
agent/
  forecasting/
    warframe_forecast_agent.py   # forecast + compare
    ask_agent.py                 # LLM Q&A
    forecast_core.py             # Monte Carlo + plots
    backtest.py                  # walk-forward evaluation
    chart_store.py               # PNG storage
    llm_client.py                # OpenAI helpers
scripts/
  backtest.py                    # CLI entry point
```

## Notes

- Forecasts are probabilistic estimates based on recent market history, not trading advice.
- REST API and A2A interfaces are not included in this package; add them when wiring a manager.
