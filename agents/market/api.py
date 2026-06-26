"""
Warframe Market Agent — FastAPI A2A Server
Scope: live orders, current prices, seller activity, portfolio tracking.
Statistics/forecasting is the Forecasting Agent's responsibility.

Endpoints:
  GET  /health                 → liveness check
  POST /query                  → natural language query (full agent loop)
  GET  /search?q=...           → item search
  GET  /item/{slug}            → item details + image_url
  GET  /orders/{slug}          → live buy/sell orders + seller active status
  GET  /portfolio              → current holdings
  GET  /trades                 → trade history
  POST /portfolio/buy          → log a purchase
  POST /portfolio/sell         → log a sale
"""

import json
import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

from tools.wfm_api import search_item, get_orders, get_item_details
from tools.db import init_db, add_holding, sell_holding, get_holdings, get_trade_history

load_dotenv()
init_db()

app = FastAPI(
    title="Warframe Market Agent",
    description="A2A market agent — live orders, current prices, seller activity, portfolio.",
    version="1.0.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── Models ────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    message: str
    session_id: str = "default"

class QueryResponse(BaseModel):
    response: str
    session_id: str

class BuyRequest(BaseModel):
    item_slug: str
    item_name: str
    quantity: int
    price_per_unit: float

class SellRequest(BaseModel):
    item_slug: str
    quantity: int
    price_per_unit: float

# ── Session store ─────────────────────────────────────────────────────────────

_sessions: dict[str, list[dict]] = {}

SYSTEM_PROMPT = """You are a Warframe Market trading sub-agent in a multi-agent pipeline.
Scope: live buy/sell orders, current prices, seller activity (are they in-game), portfolio management.
You do NOT handle forecasting or price history — that is the Forecasting Agent's job.
Return structured, concise answers. Always include seller active status when showing orders.
Currency: platinum (p)."""

TOOLS = [
    {"type": "function", "function": {"name": "search_item",      "description": "Search items by name. Returns slug + display name.",                                     "parameters": {"type": "object", "properties": {"query":     {"type": "string"}},                                                                         "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_orders",       "description": "Live top-5 buy/sell orders. Includes seller name, price, quantity, and active status.",  "parameters": {"type": "object", "properties": {"item_slug": {"type": "string"}},                                                                         "required": ["item_slug"]}}},
    {"type": "function", "function": {"name": "get_item_details", "description": "Full item info: name, image_url, description, mastery rank, ducats, tags, vaulted.",     "parameters": {"type": "object", "properties": {"item_slug": {"type": "string"}},                                                                         "required": ["item_slug"]}}},
    {"type": "function", "function": {"name": "add_holding",      "description": "Log a purchase to portfolio.",                                                           "parameters": {"type": "object", "properties": {"item_slug": {"type": "string"}, "item_name": {"type": "string"}, "quantity": {"type": "integer"}, "price_per_unit": {"type": "number"}}, "required": ["item_slug", "item_name", "quantity", "price_per_unit"]}}},
    {"type": "function", "function": {"name": "sell_holding",     "description": "Log a sale from portfolio with P&L.",                                                   "parameters": {"type": "object", "properties": {"item_slug": {"type": "string"}, "quantity": {"type": "integer"}, "price_per_unit": {"type": "number"}},           "required": ["item_slug", "quantity", "price_per_unit"]}}},
    {"type": "function", "function": {"name": "get_holdings",     "description": "Return current portfolio holdings.",                                                    "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_trade_history","description": "Return recent trade history.",                                                          "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}}},
]


def _dispatch(name: str, args: dict) -> str:
    if name == "search_item":       return json.dumps(search_item(**args))
    if name == "get_orders":        return json.dumps(get_orders(**args))
    if name == "get_item_details":  return json.dumps(get_item_details(**args))
    if name == "add_holding":       return add_holding(**args)
    if name == "sell_holding":      return sell_holding(**args)
    if name == "get_holdings":      return json.dumps(get_holdings())
    if name == "get_trade_history": return json.dumps(get_trade_history(**args))
    return f"Unknown tool: {name}"


def _run_agent(message: str, session_id: str) -> str:
    if session_id not in _sessions:
        _sessions[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    _sessions[session_id].append({"role": "user", "content": message})
    messages = list(_sessions[session_id])
    while True:
        resp = client.chat.completions.create(model="gpt-4o", messages=messages, tools=TOOLS, tool_choice="auto")
        msg = resp.choices[0].message
        messages.append(msg)
        if not msg.tool_calls:
            _sessions[session_id].append({"role": "assistant", "content": msg.content})
            return msg.content
        for tc in msg.tool_calls:
            result = _dispatch(tc.function.name, json.loads(tc.function.arguments))
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "agent": "warframe-market-agent", "version": "1.0.0"}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    try:
        return QueryResponse(response=_run_agent(req.message, req.session_id), session_id=req.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search")
def search(q: str = Query(...)):
    results = search_item(q)
    if not results:
        raise HTTPException(status_code=404, detail="No items found")
    return {"results": results}


@app.get("/item/{slug}")
def item_details(slug: str):
    try:
        return get_item_details(slug)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/orders/{slug}")
def orders(slug: str):
    result = get_orders(slug)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@app.get("/portfolio")
def portfolio():
    return {"holdings": get_holdings()}


@app.get("/trades")
def trades(limit: int = Query(20, ge=1, le=100)):
    return {"trades": get_trade_history(limit=limit)}


@app.post("/portfolio/buy")
def buy(req: BuyRequest):
    return {"status": "ok", "message": add_holding(req.item_slug, req.item_name, req.quantity, req.price_per_unit)}


@app.post("/portfolio/sell")
def sell(req: SellRequest):
    msg = sell_holding(req.item_slug, req.quantity, req.price_per_unit)
    if msg.startswith("Error"):
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
