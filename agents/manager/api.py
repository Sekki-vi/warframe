"""Manager FastAPI server — HTTP facade for Streamlit UI and subagent orchestration."""
from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents.manager.auth import get_user_info
from agents.manager.health import VERSION, health_payload
from agents.manager.orchestrator import handle_query
from agents.manager.responses import portfolio_error_response
from agents.manager import session
from agents.market import (
    buy as market_buy,
    get_portfolio,
    item_details,
    orders,
    search,
    sell as market_sell,
)
from agents.forecasting.chart_store import CHARTS_DIR

load_dotenv()

app = FastAPI(title="Warframe Manager", version=VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CHARTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/charts", StaticFiles(directory=str(CHARTS_DIR)), name="charts")


class QueryRequest(BaseModel):
    message: str
    user_id: str = "default"
    session_id: str = "default"


class BuyRequest(BaseModel):
    item_slug: str
    item_name: str
    quantity: int
    price_per_unit: float


class SellRequest(BaseModel):
    item_slug: str
    quantity: int
    price_per_unit: float


@app.get("/health")
def health():
    return health_payload()


@app.get("/user/{user_id}")
def user_info(user_id: str):
    return get_user_info(user_id)


@app.get("/search")
def search_items(q: str = Query(...)):
    results = search(q).get("results") or []
    return {"results": results}


@app.get("/item/{slug}")
def get_item(slug: str):
    try:
        return item_details(slug)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/orders/{slug}")
def get_orders(slug: str):
    result = orders(slug)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@app.get("/portfolio")
def portfolio():
    return get_portfolio()


@app.post("/portfolio/buy")
def portfolio_buy(req: BuyRequest):
    result = market_buy(req.item_slug, req.item_name, req.quantity, req.price_per_unit)
    mapped = portfolio_error_response(result)
    if "error" in mapped:
        raise HTTPException(status_code=400, detail=mapped["error"])
    return {"message": result.get("message", "ok")}


@app.post("/portfolio/sell")
def portfolio_sell(req: SellRequest):
    result = market_sell(req.item_slug, req.quantity, req.price_per_unit)
    mapped = portfolio_error_response(result)
    if "error" in mapped:
        raise HTTPException(status_code=400, detail=mapped["error"])
    return {"message": result.get("message", "ok")}


@app.post("/query")
def query(req: QueryRequest):
    try:
        return handle_query(req.message, req.user_id, req.session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/session/{session_id}")
def clear_chat_session(session_id: str):
    session.clear_session(session_id)
    return {"status": "ok"}
