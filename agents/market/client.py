"""Live Warframe Market v2 API client."""
from __future__ import annotations

import json
import time
from typing import Any

import requests

from config import WFM_API_BASE, WFM_HEADERS, WFM_ITEMS_JSON
from wfi_lookup import slugify
from wfm_catalog import fetch_items_manifest

_LAST_REQUEST = 0.0
_REQUEST_DELAY = 0.34


def _throttle() -> None:
    global _LAST_REQUEST
    elapsed = time.monotonic() - _LAST_REQUEST
    if elapsed < _REQUEST_DELAY:
        time.sleep(_REQUEST_DELAY - elapsed)
    _LAST_REQUEST = time.monotonic()


def _get_json(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{WFM_API_BASE}{path}"
    _throttle()
    resp = requests.get(url, headers=WFM_HEADERS, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _get_json_safe(path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        return _get_json(path, params)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise


def _unwrap(payload: dict[str, Any]) -> Any:
    if "data" in payload:
        return payload["data"]
    if "payload" in payload:
        return payload["payload"]
    return payload


def _normalize_user(user: dict[str, Any] | None) -> dict[str, Any]:
    user = user or {}
    return {
        "user_id": user.get("id") or user.get("_id") or "",
        "user_ingame_name": user.get("ingame_name") or user.get("ingameName") or "",
        "user_status": user.get("status") or "",
        "user_reputation": user.get("reputation") or 0,
    }


def _normalize_order(raw: dict[str, Any]) -> dict[str, Any]:
    user = _normalize_user(raw.get("user"))
    order_type = raw.get("type") or raw.get("order_type") or ""
    return {
        "order_id": raw.get("id") or raw.get("_id") or "",
        "order_type": order_type,
        "platinum": raw.get("platinum"),
        "quantity": raw.get("quantity"),
        "rank": raw.get("rank"),
        "subtype": raw.get("subtype"),
        "visible": raw.get("visible", True),
        **user,
    }


def _filter_orders(
    orders: list[dict[str, Any]],
    *,
    order_type: str = "sell",
    rank: int | None = None,
    subtype: str | None = None,
    max_platinum: int | None = None,
    online_only: bool = False,
    limit: int = 10,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for o in orders:
        if o.get("order_type") != order_type:
            continue
        if not o.get("visible", True):
            continue
        if rank is not None and o.get("rank") != rank:
            continue
        if subtype is not None and (o.get("subtype") or "") != subtype:
            continue
        if max_platinum is not None and o.get("platinum") is not None and o["platinum"] > max_platinum:
            continue
        if online_only and o.get("user_status") not in ("ingame", "online"):
            continue
        out.append(o)

    if order_type == "sell":
        out.sort(key=lambda x: (x.get("platinum") or 999999, -(x.get("user_reputation") or 0)))
    else:
        out.sort(key=lambda x: (-(x.get("platinum") or 0), -(x.get("user_reputation") or 0)))
    return out[:limit]


def get_item(slug: str) -> dict[str, Any] | None:
    """Fetch a single item via GET /v2/item/{slug}."""
    payload = _get_json_safe(f"/item/{slug}")
    if not payload:
        return None
    data = _unwrap(payload)
    if not isinstance(data, dict):
        return None
    from wfm_catalog import _normalize_item

    return _normalize_item(data)


def get_set_items(set_slug: str) -> list[dict[str, Any]]:
    """Fetch set components via GET /v2/item/{slug}/set."""
    payload = _get_json_safe(f"/item/{set_slug}/set")
    if not payload:
        return []
    data = _unwrap(payload)
    if not isinstance(data, dict):
        return []
    items = data.get("items") or []
    from wfm_catalog import _normalize_item

    return [_normalize_item(it) for it in items if isinstance(it, dict)]


def get_orders(slug: str) -> list[dict[str, Any]]:
    """Fetch all live orders for an item."""
    payload = _get_json_safe(f"/items/{slug}/orders")
    if not payload:
        return []
    data = _unwrap(payload)
    orders = data.get("orders") if isinstance(data, dict) else data
    if not isinstance(orders, list):
        return []
    return [_normalize_order(o) for o in orders]


def get_top_orders(
    slug: str,
    *,
    rank: int | None = None,
    subtype: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch top buy/sell orders for an item."""
    params: dict[str, Any] = {}
    if rank is not None:
        params["rank"] = rank
    if subtype:
        params["subtype"] = subtype
    payload = _get_json(f"/orders/item/{slug}/top", params=params or None)
    data = _unwrap(payload)
    if not isinstance(data, dict):
        return {"sell": [], "buy": []}
    sell = [_normalize_order(o) for o in data.get("sell", [])]
    buy = [_normalize_order(o) for o in data.get("buy", [])]
    return {"sell": sell, "buy": buy}


def get_statistics(slug: str) -> dict[str, Any]:
    """Fetch live/closed price statistics for an item."""
    payload = _get_json_safe(f"/items/{slug}/statistics")
    if not payload:
        return {}
    data = _unwrap(payload)
    if not isinstance(data, dict):
        return {}
    live = data.get("statistics_live") or {}
    return {
        "live": live,
        "closed": data.get("statistics_closed") or {},
    }


def resolve_slug(name_or_slug: str) -> str | None:
    """Resolve item name or slug to WFM url_name."""
    query = name_or_slug.strip().lower()
    if not query:
        return None

    by_slug = fetch_items_manifest()
    if query in by_slug:
        return query

    query_slug = slugify(name_or_slug)
    if query_slug in by_slug:
        return query_slug

    for slug, item in by_slug.items():
        item_name = (item.get("name") or "").lower()
        if item_name == name_or_slug.strip().lower():
            return slug
        if slugify(item_name) == query_slug:
            return slug

    if WFM_ITEMS_JSON.exists():
        cache = json.loads(WFM_ITEMS_JSON.read_text(encoding="utf-8"))
        for slug, item in (cache.get("by_slug") or {}).items():
            if slugify(item.get("name", "")) == query_slug:
                return slug
    return None


def get_live_orders(
    slug: str,
    *,
    order_type: str = "sell",
    rank: int | None = None,
    subtype: str | None = None,
    max_platinum: int | None = None,
    online_only: bool = False,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Fetch and filter live orders."""
    orders = get_orders(slug)
    if not orders:
        top = get_top_orders(slug, rank=rank, subtype=subtype)
        orders = top.get(order_type, [])
    return _filter_orders(
        orders,
        order_type=order_type,
        rank=rank,
        subtype=subtype,
        max_platinum=max_platinum,
        online_only=online_only,
        limit=limit,
    )


def get_price_summary(
    slug: str,
    *,
    rank: int | None = None,
    subtype: str | None = None,
) -> dict[str, Any]:
    """Combine top orders and statistics for a price overview."""
    top = get_top_orders(slug, rank=rank, subtype=subtype)
    stats = get_statistics(slug)
    sell_prices = [o["platinum"] for o in top.get("sell", []) if o.get("platinum") is not None]
    buy_prices = [o["platinum"] for o in top.get("buy", []) if o.get("platinum") is not None]
    return {
        "slug": slug,
        "cheapest_sell": min(sell_prices) if sell_prices else None,
        "highest_buy": max(buy_prices) if buy_prices else None,
        "top_sell": top.get("sell", [])[:5],
        "top_buy": top.get("buy", [])[:5],
        "statistics": stats.get("live") or {},
    }
