"""Resolve optional public base URL for chart links."""

from __future__ import annotations

import os

DEFAULT_BASE_URL = "http://127.0.0.1:8765"


def public_base_url() -> str:
    configured = os.environ.get("AGENT_PUBLIC_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    return DEFAULT_BASE_URL
