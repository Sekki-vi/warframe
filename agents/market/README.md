# Market Agent

Library subagent for live Warframe Market buy/sell orders, current prices, seller activity, and portfolio tracking. Forecasting and price history are handled by the Forecasting agent.

## Usage

Run from the repo root with `.env` loaded (needs `OPENAI_API_KEY` for `answer()`):

```python
from dotenv import load_dotenv
load_dotenv()

from agents.market import answer, search, orders, item_details, get_portfolio, buy, sell

# Direct WFM calls (no LLM)
hits = search("mag prime")
print(hits["results"][0]["slug"])

book = orders("mag_prime_set")
print(book["cheapest_sell_orders"])

# Natural-language agent loop
result = answer("What are the cheapest sell orders for mag prime set?")
print(result["response"])
```

## Public API

| Function | Description |
|----------|-------------|
| `answer(message, session_id="default")` | LLM agent loop with WFM + portfolio tools |
| `search(query)` | Item search by name |
| `item_details(slug)` | Full item metadata |
| `orders(slug)` | Live top buy/sell orders + seller status |
| `get_portfolio()` | Current holdings |
| `get_trades(limit=20)` | Trade history |
| `buy(...)` / `sell(...)` | Log portfolio transactions |

Portfolio data is stored in `agents/market/trades.db` (created on first use).

## Manager integration

```python
from agents.market import answer as market_answer

market_result = market_answer(
    "cheapest sell orders for ash prime set",
    session_id=user_id,
)
reply = market_result["response"]
```
