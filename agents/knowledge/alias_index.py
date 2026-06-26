"""Load alias + taxonomy index for keyword retrieval."""
from __future__ import annotations

import json
from typing import Any

from config import ALIAS_INDEX_JSON


def load_alias_index() -> dict[str, Any]:
    if not ALIAS_INDEX_JSON.exists():
        raise FileNotFoundError(
            f"Alias index not found at {ALIAS_INDEX_JSON}. "
            "Place a pre-built alias_index.json in data/processed/."
        )
    return json.loads(ALIAS_INDEX_JSON.read_text(encoding="utf-8"))
