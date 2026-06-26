"""Forecasting agent for Warframe Market item prices."""

from __future__ import annotations

import base64
import json
import os
import re
import time
from difflib import get_close_matches
from functools import lru_cache
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import numpy as np

from .chart_store import chart_url, save_chart
from .forecast_core import downsample, forecast, make_comparison_plot, make_plot
from .public_url import public_base_url

API_V1_BASE = "https://api.warframe.market/v1"
API_V2_BASE = "https://api.warframe.market/v2"
API_TIMEOUT = int(os.getenv("WFM_API_TIMEOUT", "45"))
API_RETRIES = int(os.getenv("WFM_API_RETRIES", "3"))
PRICE_FIELDS = {"median", "avg_price", "wa_price", "closed_price", "moving_avg"}
TIMEFRAMES = {"48hours", "90days"}


class WarframeMarketError(ValueError):
    """Raised when the forecasting agent cannot fetch or prepare market data."""


def _normalize(value: str) -> str:
    value = value.strip().lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _slugify(value: str) -> str:
    return _normalize(value).replace(" ", "_")


def _get_json(path: str, *, base_url: str = API_V1_BASE) -> dict[str, Any]:
    url = f"{base_url}{path}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "warframe-forecast-agent/0.1",
            "Platform": "pc",
            "Language": "en",
        },
    )
    last_exc: Exception | None = None
    for attempt in range(API_RETRIES):
        try:
            with urlopen(request, timeout=API_TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise WarframeMarketError(
                f"Warframe Market API returned HTTP {exc.code} for {url}"
            ) from exc
        except (URLError, TimeoutError) as exc:
            last_exc = exc
            if attempt + 1 < API_RETRIES:
                time.sleep(1.5 * (attempt + 1))
                continue
        except json.JSONDecodeError as exc:
            raise WarframeMarketError("Warframe Market API returned invalid JSON") from exc

    raise WarframeMarketError(f"Could not reach Warframe Market API: {last_exc}") from last_exc


@lru_cache(maxsize=1)
def _items() -> list[dict[str, Any]]:
    data = _get_json("/items", base_url=API_V2_BASE).get("data")
    if not isinstance(data, list) or not data:
        raise WarframeMarketError("Warframe Market API returned no item list")
    items = []
    for item in data:
        slug = item.get("slug")
        name = item.get("i18n", {}).get("en", {}).get("name")
        if slug and name:
            items.append(
                {
                    "url_name": slug,
                    "item_name": name,
                    "thumb": item.get("i18n", {}).get("en", {}).get("thumb"),
                }
            )
    if not items:
        raise WarframeMarketError("Warframe Market API returned no usable item names")
    return items


def resolve_item(query: str) -> dict[str, Any]:
    """Resolve a user-facing item query into a Warframe Market item record."""
    if not query or not query.strip():
        raise WarframeMarketError("Enter a Warframe Market item name")

    items = _items()
    by_slug = {item["url_name"]: item for item in items if item.get("url_name")}
    candidate_slug = _slugify(query)
    if candidate_slug in by_slug:
        return by_slug[candidate_slug]

    normalized_query = _normalize(query)
    names = {
        _normalize(item.get("item_name", "")): item
        for item in items
        if item.get("item_name")
    }
    if normalized_query in names:
        return names[normalized_query]

    slug_names = {_normalize(item["url_name"].replace("_", " ")): item for item in by_slug.values()}
    searchable = {**slug_names, **names}
    close = get_close_matches(normalized_query, searchable.keys(), n=1, cutoff=0.62)
    if close:
        return searchable[close[0]]

    raise WarframeMarketError(f"Could not find a Warframe Market item matching '{query}'")


def _statistics(url_name: str) -> dict[str, Any]:
    safe_slug = quote(url_name, safe="")
    payload = _get_json(f"/items/{safe_slug}/statistics").get("payload", {})
    closed = payload.get("statistics_closed") or payload.get("statistics")
    if not isinstance(closed, dict):
        raise WarframeMarketError(f"No completed-trade statistics found for {url_name}")
    return closed


def _extract_series(
    rows: list[dict[str, Any]],
    price_field: str,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    points: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda entry: entry.get("datetime", "")):
        value = row.get(price_field)
        if value is None:
            continue
        try:
            price = float(value)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        points.append(
            {
                "datetime": row.get("datetime"),
                "price": price,
                "volume": row.get("volume", 0),
            }
        )

    if len(points) < 4:
        raise WarframeMarketError(
            "Not enough market history to forecast this item. Try another item or timeframe."
        )
    return np.array([point["price"] for point in points], dtype=float), points


def _series_stats(series: np.ndarray) -> dict[str, float]:
    return {
        "min": float(series.min()),
        "max": float(series.max()),
        "mean": float(series.mean()),
        "median": float(np.median(series)),
        "last": float(series[-1]),
    }


def _attach_chart_urls(result: dict[str, Any], plot_png: bytes, base_url: str | None) -> dict[str, Any]:
    chart_id = save_chart(plot_png)
    resolved_base = (base_url or public_base_url()).rstrip("/")
    result["chart_id"] = chart_id
    result["plot_url"] = chart_url(chart_id, resolved_base)
    result["plot_base64"] = base64.b64encode(plot_png).decode("ascii")
    return result


def _load_item_series(
    item_query: str,
    *,
    timeframe: str,
    price_field: str,
    points: int,
) -> dict[str, Any]:
    if timeframe not in TIMEFRAMES:
        raise WarframeMarketError("timeframe must be 48hours or 90days")
    if price_field not in PRICE_FIELDS:
        raise WarframeMarketError(
            "price_field must be median, avg_price, wa_price, closed_price, or moving_avg"
        )

    item = resolve_item(item_query)
    url_name = item["url_name"]
    closed = _statistics(url_name)
    rows = closed.get(timeframe)
    if not isinstance(rows, list) or not rows:
        raise WarframeMarketError(f"No {timeframe} statistics found for {item['item_name']}")

    raw_series, market_points = _extract_series(rows, price_field)
    series = downsample(raw_series, points)
    item_name = item.get("item_name", url_name.replace("_", " ").title())
    return {
        "item": {
            "item_name": item_name,
            "url_name": url_name,
            "source_url": f"https://warframe.market/items/{url_name}",
        },
        "market": {
            "timeframe": timeframe,
            "price_field": price_field,
            "first_datetime": market_points[0]["datetime"],
            "last_datetime": market_points[-1]["datetime"],
        },
        "raw_series": raw_series,
        "series": series,
        "market_points": market_points,
        "history_stats": _series_stats(raw_series),
    }


def forecast_item(
    item_query: str,
    *,
    timeframe: str = "90days",
    price_field: str = "median",
    points: int = 60,
    horizon: int = 12,
    paths: int = 5000,
    recent_frac: float = 0.35,
    seed: int = 42,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Forecast a Warframe Market item from completed-trade price statistics."""
    loaded = _load_item_series(
        item_query,
        timeframe=timeframe,
        price_field=price_field,
        points=points,
    )
    series = loaded["series"]
    fc = forecast(series, horizon, paths, recent_frac, seed)
    item_name = loaded["item"]["item_name"]
    metric_label = price_field.replace("_", " ")
    plot_png = make_plot(
        series,
        fc,
        "platinum",
        f"{item_name} {metric_label} forecast",
        history_label=f"{metric_label.title()} history",
    )

    stats = {
        "points": len(series),
        "raw_points": len(loaded["raw_series"]),
        "last": fc["last"],
        "drift": fc["drift"],
        "sigma": fc["sigma"],
        "mean_end": float(fc["mean"][-1]),
        "ci80_low": float(fc["lo80"][-1]),
        "ci80_high": float(fc["hi80"][-1]),
        "ci95_low": float(fc["lo95"][-1]),
        "ci95_high": float(fc["hi95"][-1]),
        "history": loaded["history_stats"],
    }

    result = {
        "unit_label": "platinum",
        "calibrated": True,
        "series": series.tolist(),
        "stats": stats,
        "agent": "warframe_forecasting_agent",
        "skill": "forecast_item",
        "item": loaded["item"],
        "market": loaded["market"],
    }
    return _attach_chart_urls(result, plot_png, base_url)


def compare_items(
    item_queries: list[str],
    *,
    timeframe: str = "90days",
    price_field: str = "median",
    points: int = 60,
    horizon: int = 12,
    paths: int = 5000,
    recent_frac: float = 0.35,
    seed: int = 42,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Compare at least two Warframe Market items on price history and forecast stats."""
    cleaned = [query.strip() for query in item_queries if query and query.strip()]
    if len(cleaned) < 2:
        raise WarframeMarketError("Provide at least two items to compare")

    entries: list[dict[str, Any]] = []
    plot_series: list[tuple[str, np.ndarray]] = []
    for query in cleaned:
        loaded = _load_item_series(
            query,
            timeframe=timeframe,
            price_field=price_field,
            points=points,
        )
        series = loaded["series"]
        fc = forecast(series, horizon, paths, recent_frac, seed)
        plot_series.append((loaded["item"]["item_name"], series))
        entries.append(
            {
                "item": loaded["item"],
                "market": loaded["market"],
                "history_stats": loaded["history_stats"],
                "forecast_stats": {
                    "last": fc["last"],
                    "drift": fc["drift"],
                    "sigma": fc["sigma"],
                    "mean_end": float(fc["mean"][-1]),
                    "ci80_low": float(fc["lo80"][-1]),
                    "ci80_high": float(fc["hi80"][-1]),
                    "ci95_low": float(fc["lo95"][-1]),
                    "ci95_high": float(fc["hi95"][-1]),
                },
            }
        )

    metric_label = price_field.replace("_", " ")
    title = f"Compare {metric_label} — {', '.join(entry['item']['item_name'] for entry in entries)}"
    plot_png = make_comparison_plot(
        plot_series,
        "platinum",
        title,
        metric_label=metric_label,
    )

    result = {
        "unit_label": "platinum",
        "agent": "warframe_forecasting_agent",
        "skill": "compare_items",
        "market": {
            "timeframe": timeframe,
            "price_field": price_field,
        },
        "items": entries,
        "comparison": {
            "count": len(entries),
            "cheapest_last": min(entries, key=lambda entry: entry["history_stats"]["last"]),
            "highest_last": max(entries, key=lambda entry: entry["history_stats"]["last"]),
            "cheapest_median": min(entries, key=lambda entry: entry["history_stats"]["median"]),
            "highest_median": max(entries, key=lambda entry: entry["history_stats"]["median"]),
        },
    }
    return _attach_chart_urls(result, plot_png, base_url)
