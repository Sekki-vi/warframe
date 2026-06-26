# Market Agent

FastAPI A2A server. Handles live buy/sell orders, current prices, seller activity, and portfolio tracking.

## Run

```bash
pip install -r requirements.txt
cp .env.example .env   # add your OPENAI_API_KEY
uvicorn api:app --host 0.0.0.0 --port 8000
```

## Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Liveness check |
| POST | /query | Natural language query `{message, session_id}` |
| GET | /search?q= | Item search |
| GET | /item/{slug} | Item details + image_url |
| GET | /orders/{slug} | Live buy/sell orders + seller status |
| GET | /portfolio | Current holdings |
| POST | /portfolio/buy | Log a purchase |
| POST | /portfolio/sell | Log a sale with P&L |

## Manager Integration

```python
import requests
r = requests.post("http://localhost:8000/query",
    json={"message": "price of ash prime set", "session_id": "user-abc"})
print(r.json()["response"])
```
