"""
Warframe Market Agent — API wrapper.
Scope: item search, item details, live buy/sell orders only.
Statistics/forecasting is handled by the Forecasting Agent (separate sub-agent).
"""
from __future__ import annotations

import requests

BASE_V2 = "https://api.warframe.market/v2"
IMAGE_BASE = "https://warframe.market/static/assets/"

_HEADERS = {"Platform": "pc", "Language": "en", "Accept": "application/json"}

_items_cache: list[dict] | None = None


def _get_all_items() -> list[dict]:
    global _items_cache
    if _items_cache is None:
        resp = requests.get(f"{BASE_V2}/items", headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        _items_cache = [
            {"slug": i["slug"], "name": i["i18n"]["en"]["name"]}
            for i in resp.json()["data"]
        ]
    return _items_cache


def search_item(query: str) -> list[dict]:
    """Return top 5 items matching query (case-insensitive)."""
    query = query.lower().strip()
    return [
        i for i in _get_all_items()
        if query in i["name"].lower() or query in i["slug"].lower()
    ][:5]


def get_item_details(item_slug: str) -> dict:
    """Full item info: name, image, description, tags, mastery rank, ducats, wiki."""
    resp = requests.get(f"{BASE_V2}/items/{item_slug}", headers=_HEADERS, timeout=10)
    resp.raise_for_status()
    d = resp.json()["data"]
    i18n = d.get("i18n", {}).get("en", {})
    return {
        "slug":         d["slug"],
        "name":         i18n.get("name", d["slug"]),
        "description":  i18n.get("description", ""),
        "wiki_link":    i18n.get("wikiLink", ""),
        "image_url":    IMAGE_BASE + i18n["icon"]  if i18n.get("icon")  else None,
        "thumb_url":    IMAGE_BASE + i18n["thumb"] if i18n.get("thumb") else None,
        "tags":         d.get("tags", []),
        "ducats":       d.get("ducats"),
        "trading_tax":  d.get("tradingTax"),
        "mastery_rank": d.get("reqMasteryRank"),
        "vaulted":      d.get("vaulted", False),
        "tradable":     d.get("tradable", True),
    }


def get_orders(item_slug: str) -> dict:
    """
    Live top-5 buy and sell orders from Warframe Market.
    Public v2 endpoint — no auth needed.
    Includes seller name and online status for each order.
    Status values: 'ingame' (actively playing), 'online' (on site), 'offline'.
    """
    resp = requests.get(
        f"{BASE_V2}/orders/item/{item_slug}/top",
        headers=_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()["data"]

    sell_orders = data.get("sell", [])
    buy_orders  = data.get("buy", [])

    def fmt(o: dict) -> dict:
        user = o.get("user", {})
        status = user.get("status", "unknown")
        return {
            "price_platinum": o["platinum"],
            "quantity":       o["quantity"],
            "seller":         user.get("ingameName", user.get("slug", "unknown")),
            "status":         status,
            "active":         status == "ingame",
        }

    result: dict = {
        "item_slug":            item_slug,
        "cheapest_sell_orders": [fmt(o) for o in sell_orders],
        "highest_buy_orders":   [fmt(o) for o in buy_orders],
    }

    if sell_orders:
        result["best_sell_price_platinum"] = sell_orders[0]["platinum"]
    if buy_orders:
        result["best_buy_price_platinum"] = buy_orders[0]["platinum"]
    if sell_orders and buy_orders:
        result["spread_platinum"] = sell_orders[0]["platinum"] - buy_orders[0]["platinum"]

    return result
