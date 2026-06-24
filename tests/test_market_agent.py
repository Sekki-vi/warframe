#!/usr/bin/env python3
"""Tests for agents.market live API helpers (mocked HTTP)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.market.live import check_listed, is_listed_on_market
from agents.market.set_parts import get_set_parts, resolve_set_slug


class MarketLiveTests(unittest.TestCase):
    @patch("agents.market.client.get_item")
    def test_listed_on_market_true(self, mock_get_item):
        mock_get_item.return_value = {"slug": "ash_prime_set", "tradable": True, "setRoot": True}
        self.assertTrue(is_listed_on_market("ash_prime_set"))
        self.assertTrue(check_listed("ash_prime_set"))

    @patch("agents.market.client.get_item")
    def test_listed_on_market_false(self, mock_get_item):
        mock_get_item.return_value = {"slug": "wisp", "tradable": False}
        self.assertFalse(is_listed_on_market("wisp"))

    @patch("agents.market.client.get_item")
    def test_listed_on_market_missing(self, mock_get_item):
        mock_get_item.return_value = None
        self.assertFalse(check_listed("nonexistent_item"))


class SetPartsTests(unittest.TestCase):
    @patch("agents.market.client.get_set_items")
    @patch("agents.market.client.get_item")
    def test_get_set_parts_filters_tradable(self, mock_get_item, mock_get_set):
        mock_get_item.return_value = {"slug": "nova_prime_set", "tradable": True, "setRoot": True}
        mock_get_set.return_value = [
            {"slug": "nova_prime_set", "tradable": True, "setRoot": True, "name": "Nova Prime Set"},
            {
                "slug": "nova_prime_blueprint",
                "tradable": True,
                "name": "Nova Prime Blueprint",
                "ducats": 45,
            },
            {
                "slug": "nova_prime_chassis_blueprint",
                "tradable": True,
                "name": "Nova Prime Chassis Blueprint",
            },
            {"slug": "internal_only", "tradable": False, "name": "Internal"},
        ]
        parts = get_set_parts("nova_prime", "nova_prime_set")
        slugs = {p["slug"] for p in parts}
        self.assertIn("nova_prime_blueprint", slugs)
        self.assertIn("nova_prime_chassis_blueprint", slugs)
        self.assertNotIn("internal_only", slugs)
        self.assertNotIn("nova_prime_set", slugs)

    def test_resolve_set_slug_from_wfm(self):
        self.assertEqual(resolve_set_slug("nova_prime", "nova_prime_set"), "nova_prime_set")


if __name__ == "__main__":
    unittest.main()
