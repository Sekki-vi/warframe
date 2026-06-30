"""SQLite persistence layer for holdings and trade history."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "trades.db"
SCHEMA_PATH = Path(__file__).parent.parent / "schema.sql"


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _normalize_slug(item_slug: str) -> str:
    """Canonical Warframe Market slug form: lowercase with underscores.

    Holdings were historically stored with hyphenated slugs (e.g.
    "volt-prime-set") which never matched the underscore form WFM and the sell
    flow use ("volt_prime_set"), so they couldn't be sold.
    """
    return (item_slug or "").strip().lower().replace("-", "_")


def _migrate_legacy_slugs(con: sqlite3.Connection) -> None:
    """Normalize any legacy non-canonical slugs in place (idempotent)."""
    con.execute("UPDATE trades SET item_slug = REPLACE(LOWER(item_slug), '-', '_')")
    for r in con.execute(
        "SELECT id, item_slug, quantity, avg_buy_price FROM holdings"
    ).fetchall():
        canon = _normalize_slug(r["item_slug"])
        if canon == r["item_slug"]:
            continue
        dup = con.execute(
            "SELECT id, quantity, avg_buy_price FROM holdings WHERE item_slug = ? AND id <> ?",
            (canon, r["id"]),
        ).fetchone()
        if dup:
            # A canonical row already exists — merge the legacy one into it.
            total = dup["quantity"] + r["quantity"]
            avg = (
                round(
                    (dup["avg_buy_price"] * dup["quantity"] + r["avg_buy_price"] * r["quantity"])
                    / total,
                    2,
                )
                if total
                else r["avg_buy_price"]
            )
            con.execute(
                "UPDATE holdings SET quantity = ?, avg_buy_price = ? WHERE id = ?",
                (total, avg, dup["id"]),
            )
            con.execute("DELETE FROM holdings WHERE id = ?", (r["id"],))
        else:
            con.execute(
                "UPDATE holdings SET item_slug = ? WHERE id = ?", (canon, r["id"])
            )


def init_db() -> None:
    """Create tables if they don't exist and normalize any legacy slugs."""
    with _conn() as con:
        con.executescript(SCHEMA_PATH.read_text())
        _migrate_legacy_slugs(con)


def add_holding(item_slug: str, item_name: str, quantity: int, price_per_unit: float) -> str:
    """Add or update a holding. Logs a buy trade."""
    item_slug = _normalize_slug(item_slug)
    with _conn() as con:
        existing = con.execute(
            "SELECT * FROM holdings WHERE item_slug = ?", (item_slug,)
        ).fetchone()

        if existing:
            old_qty = existing["quantity"]
            old_avg = existing["avg_buy_price"]
            new_qty = old_qty + quantity
            new_avg = round((old_avg * old_qty + price_per_unit * quantity) / new_qty, 2)
            con.execute(
                "UPDATE holdings SET quantity = ?, avg_buy_price = ? WHERE item_slug = ?",
                (new_qty, new_avg, item_slug),
            )
            msg = f"Updated holding: {item_name} now {new_qty}x @ {new_avg}p avg"
        else:
            con.execute(
                "INSERT INTO holdings (item_slug, item_name, quantity, avg_buy_price) VALUES (?,?,?,?)",
                (item_slug, item_name, quantity, round(price_per_unit, 2)),
            )
            msg = f"Added holding: {quantity}x {item_name} @ {price_per_unit}p"

        con.execute(
            "INSERT INTO trades (item_slug, item_name, trade_type, quantity, price_per_unit, total_value) VALUES (?,?,?,?,?,?)",
            (item_slug, item_name, "buy", quantity, price_per_unit, round(quantity * price_per_unit, 2)),
        )
    return msg


def sell_holding(item_slug: str, quantity: int, price_per_unit: float) -> str:
    """Reduce or remove a holding. Logs a sell trade. Returns P&L."""
    item_slug = _normalize_slug(item_slug)
    with _conn() as con:
        existing = con.execute(
            "SELECT * FROM holdings WHERE item_slug = ?", (item_slug,)
        ).fetchone()

        if not existing:
            return f"Error: No holding found for {item_slug}"

        if existing["quantity"] < quantity:
            return f"Error: You only hold {existing['quantity']}x, cannot sell {quantity}x"

        avg_cost = existing["avg_buy_price"]
        profit = round((price_per_unit - avg_cost) * quantity, 2)
        profit_str = f"+{profit}p" if profit >= 0 else f"{profit}p"

        new_qty = existing["quantity"] - quantity
        if new_qty == 0:
            con.execute("DELETE FROM holdings WHERE item_slug = ?", (item_slug,))
        else:
            con.execute(
                "UPDATE holdings SET quantity = ? WHERE item_slug = ?",
                (new_qty, item_slug),
            )

        con.execute(
            "INSERT INTO trades (item_slug, item_name, trade_type, quantity, price_per_unit, total_value) VALUES (?,?,?,?,?,?)",
            (item_slug, existing["item_name"], "sell", quantity, price_per_unit, round(quantity * price_per_unit, 2)),
        )

    return (
        f"Sold {quantity}x {existing['item_name']} @ {price_per_unit}p. "
        f"P&L vs avg cost ({avg_cost}p): {profit_str}"
    )


def remove_holding(item_slug: str) -> str:
    """Delete a holding outright without logging a sell trade."""
    item_slug = _normalize_slug(item_slug)
    with _conn() as con:
        existing = con.execute(
            "SELECT item_name FROM holdings WHERE item_slug = ?", (item_slug,)
        ).fetchone()
        if not existing:
            return f"Error: No holding found for {item_slug}"
        con.execute("DELETE FROM holdings WHERE item_slug = ?", (item_slug,))
    return f"Removed holding: {existing['item_name']}"


def get_holdings() -> list[dict]:
    """Return all current holdings."""
    with _conn() as con:
        rows = con.execute(
            "SELECT item_slug, item_name, quantity, avg_buy_price, acquired_at FROM holdings ORDER BY item_name"
        ).fetchall()
    return [dict(r) for r in rows]


def get_trade_history(limit: int = 20) -> list[dict]:
    """Return the most recent trades."""
    with _conn() as con:
        rows = con.execute(
            "SELECT item_name, trade_type, quantity, price_per_unit, total_value, traded_at "
            "FROM trades ORDER BY traded_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
