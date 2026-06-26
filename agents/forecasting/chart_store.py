"""Persist generated chart PNGs."""

from __future__ import annotations

import uuid
from pathlib import Path

CHARTS_DIR = Path(__file__).resolve().parent / "charts"


def ensure_charts_dir() -> Path:
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    return CHARTS_DIR


def save_chart(png_bytes: bytes) -> str:
    chart_id = uuid.uuid4().hex
    path = ensure_charts_dir() / f"{chart_id}.png"
    path.write_bytes(png_bytes)
    return chart_id


def chart_path(chart_id: str) -> Path:
    safe_id = chart_id.replace("-", "").lower()
    if len(safe_id) != 32 or any(c not in "0123456789abcdef" for c in safe_id):
        raise ValueError("Invalid chart id")
    return ensure_charts_dir() / f"{safe_id}.png"


def chart_url(chart_id: str, base_url: str) -> str:
    return f"{base_url.rstrip('/')}/charts/{chart_id}.png"
