"""Import order CSV into SQLite for seller/order lookup."""
from __future__ import annotations

import argparse
import sqlite3
from typing import Any

import pandas as pd

from aggregate_orders import _normalize_rank, _normalize_subtype
from config import ORDERS_CSV, ORDERS_DB

KEEP_COLUMNS = [
    "order_id",
    "slug",
    "item_name",
    "is_prime_part",
    "order_type",
    "platinum",
    "quantity",
    "visible",
    "rank",
    "subtype",
    "user_id",
    "user_ingame_name",
    "user_status",
    "user_reputation",
    "pulled_at",
]

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    item_name TEXT,
    is_prime_part INTEGER NOT NULL DEFAULT 0,
    order_type TEXT NOT NULL,
    platinum REAL NOT NULL,
    quantity INTEGER NOT NULL,
    visible INTEGER NOT NULL DEFAULT 1,
    rank INTEGER,
    subtype TEXT,
    user_id TEXT,
    user_ingame_name TEXT,
    user_status TEXT,
    user_reputation INTEGER,
    pulled_at TEXT
)
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_orders_lookup "
    "ON orders (slug, order_type, rank, subtype, platinum)",
    "CREATE INDEX IF NOT EXISTS idx_orders_slug_type_price "
    "ON orders (slug, order_type, platinum)",
]


def _prepare_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    out = chunk.copy()
    out["rank"] = out["rank"].apply(_normalize_rank)
    out["subtype"] = out["subtype"].apply(_normalize_subtype)
    out["is_prime_part"] = out["is_prime_part"].astype(str).str.lower().eq("true").astype(int)
    out["visible"] = out["visible"].astype(str).str.lower().eq("true").astype(int)
    out["platinum"] = out["platinum"].astype(float)
    out["quantity"] = out["quantity"].astype(int)
    out["user_reputation"] = pd.to_numeric(out["user_reputation"], errors="coerce").astype("Int64")
    return out[KEEP_COLUMNS]


def build_orders_db(*, force: bool = False) -> dict[str, Any]:
    if ORDERS_DB.exists() and not force:
        with sqlite3.connect(ORDERS_DB) as conn:
            count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        print(f"Orders DB already exists ({count} rows) -> {ORDERS_DB}")
        return {"path": str(ORDERS_DB), "rows": count, "skipped": True}

    if not ORDERS_CSV.exists():
        raise FileNotFoundError(f"Orders CSV not found: {ORDERS_CSV}")

    ORDERS_DB.parent.mkdir(parents=True, exist_ok=True)
    if ORDERS_DB.exists():
        ORDERS_DB.unlink()

    print(f"Building orders DB from {ORDERS_CSV} ...")
    total = 0
    with sqlite3.connect(ORDERS_DB) as conn:
        conn.execute(CREATE_TABLE)
        for chunk in pd.read_csv(ORDERS_CSV, chunksize=50_000, low_memory=False):
            prepared = _prepare_chunk(chunk)
            prepared.to_sql("orders", conn, if_exists="append", index=False)
            total += len(prepared)
            print(f"  imported {total} rows ...", flush=True)
        for stmt in INDEXES:
            conn.execute(stmt)
        conn.commit()

    print(f"Orders DB ready: {total} rows -> {ORDERS_DB}")
    return {"path": str(ORDERS_DB), "rows": total, "skipped": False}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SQLite orders database from CSV")
    parser.add_argument("--force", action="store_true", help="Rebuild even if DB exists")
    args = parser.parse_args()
    build_orders_db(force=args.force)


if __name__ == "__main__":
    main()
