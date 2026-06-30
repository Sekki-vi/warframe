"""Forecasting agent helper tests (pure functions, no network/LLM)."""
from __future__ import annotations

import unittest

from agents.forecasting.ask_agent import _looks_like_question, item_names_from_result


class ForecastHelperTests(unittest.TestCase):
    def test_item_names_single(self) -> None:
        self.assertEqual(
            item_names_from_result({"item": {"item_name": "Saryn Prime Set"}}),
            ["Saryn Prime Set"],
        )

    def test_item_names_compare_dedup(self) -> None:
        result = {
            "items": [
                {"item": {"item_name": "Volt Prime Set"}},
                {"item": {"item_name": "Volt Prime Set"}},
                {"item": {"item_name": "Mesa Prime Set"}},
            ]
        }
        self.assertEqual(item_names_from_result(result), ["Volt Prime Set", "Mesa Prime Set"])

    def test_item_names_empty(self) -> None:
        self.assertEqual(item_names_from_result({}), [])

    def test_looks_like_question(self) -> None:
        self.assertTrue(_looks_like_question("is now a good time to buy?"))
        self.assertTrue(_looks_like_question("when should I sell my Mesa Prime"))
        self.assertFalse(_looks_like_question("Saryn Prime Set"))


if __name__ == "__main__":
    unittest.main()
