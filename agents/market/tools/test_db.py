"""Slug normalization + legacy-slug migration tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.market.tools import db


class SlugMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.mkdtemp()
        self._patch = patch.object(db, "DB_PATH", Path(self._dir) / "trades.db")
        self._patch.start()
        db.init_db()

    def tearDown(self) -> None:
        self._patch.stop()

    def _insert(self, slug: str, qty: int, avg: float) -> None:
        with db._conn() as con:
            con.execute(
                "INSERT INTO holdings (item_slug, item_name, quantity, avg_buy_price) VALUES (?,?,?,?)",
                (slug, "Volt Prime Set", qty, avg),
            )

    def test_normalize_slug(self) -> None:
        self.assertEqual(db._normalize_slug("Volt-Prime-Set"), "volt_prime_set")
        self.assertEqual(db._normalize_slug("  saryn_prime_set "), "saryn_prime_set")

    def test_legacy_hyphen_holding_becomes_sellable(self) -> None:
        self._insert("volt-prime-set", 1, 63.0)
        db.init_db()  # runs the migration

        holdings = db.get_holdings()
        self.assertEqual(holdings[0]["item_slug"], "volt_prime_set")
        # The sell flow uses the underscore form — it now matches.
        self.assertTrue(db.sell_holding("volt_prime_set", 1, 70.0).startswith("Sold"))

    def test_migration_merges_duplicate_slugs(self) -> None:
        self._insert("volt_prime_set", 1, 50.0)
        self._insert("volt-prime-set", 1, 70.0)
        db.init_db()

        holdings = db.get_holdings()
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0]["quantity"], 2)
        self.assertEqual(holdings[0]["avg_buy_price"], 60.0)


if __name__ == "__main__":
    unittest.main()
