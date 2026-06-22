"""Query individual market orders by slug for seller/trading lookup."""
from __future__ import annotations

import sqlite3
from typing import Any

from config import ORDERS_DB


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    if d.get("is_prime_part") is not None:
        d["is_prime_part"] = bool(d["is_prime_part"])
    if d.get("visible") is not None:
        d["visible"] = bool(d["visible"])
    return d


def find_orders(
    slug: str,
    *,
    order_type: str = "sell",
    rank: int | None = None,
    subtype: str | None = None,
    max_platinum: int | None = None,
    online_only: bool = False,
    limit: int = 10,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Return matching orders sorted by platinum ascending (cheapest first)."""
    path = db_path or str(ORDERS_DB)
    if not ORDERS_DB.exists() and db_path is None:
        raise FileNotFoundError(
            f"Orders DB not found at {ORDERS_DB}. Run build_orders_db.py first."
        )

    clauses = ["slug = ?", "order_type = ?", "visible = 1"]
    params: list[Any] = [slug, order_type]

    if rank is None:
        clauses.append("rank IS NULL")
    else:
        clauses.append("rank = ?")
        params.append(rank)

    if subtype is None:
        clauses.append("subtype IS NULL")
    else:
        clauses.append("subtype = ?")
        params.append(subtype)

    if max_platinum is not None:
        clauses.append("platinum <= ?")
        params.append(max_platinum)

    if online_only:
        clauses.append("user_status IN ('ingame', 'online')")

    sql = (
        "SELECT order_id, slug, item_name, is_prime_part, order_type, "
        "platinum, quantity, visible, rank, subtype, "
        "user_id, user_ingame_name, user_status, user_reputation, pulled_at "
        f"FROM orders WHERE {' AND '.join(clauses)} "
        "ORDER BY platinum ASC, user_reputation DESC "
        f"LIMIT ?"
    )
    params.append(limit)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]
