"""SQLite persistence layer for holdings and trade history."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "trades.db"
SCHEMA_PATH = Path(__file__).parent.parent / "schema.sql"


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    """Create tables if they don't exist."""
    with _conn() as con:
        con.executescript(SCHEMA_PATH.read_text())


def add_holding(item_slug: str, item_name: str, quantity: int, price_per_unit: float) -> str:
    """Add or update a holding. Logs a buy trade."""
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
