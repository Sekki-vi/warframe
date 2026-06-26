CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_slug TEXT NOT NULL UNIQUE,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    avg_buy_price REAL NOT NULL,
    acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_slug TEXT NOT NULL,
    item_name TEXT NOT NULL,
    trade_type TEXT CHECK(trade_type IN ('buy','sell')),
    quantity INTEGER NOT NULL,
    price_per_unit REAL NOT NULL,
    total_value REAL NOT NULL,
    traded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
