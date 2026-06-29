"""Market agent tier enrichment tests."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from agents.market.agent import _build_item_source, answer, clear_session


SARYN_SET_DETAILS = {
    "slug": "saryn_prime_set",
    "name": "Saryn Prime Set",
    "description": "Prime warframe set.",
    "wiki_link": "https://wiki.warframe.com/w/Saryn_Prime",
    "image_url": "https://example.com/saryn.png",
    "tags": ["warframe"],
}


class MarketAgentTierTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_session("tier-test")

    def tearDown(self) -> None:
        clear_session("tier-test")

    @patch("agents.market.agent.get_item_details", return_value=SARYN_SET_DETAILS)
    @patch("agents.market.agent.lookup_tier_from_wfm", return_value="S")
    def test_build_item_source_includes_tier(self, _mock_tier, _mock_details) -> None:
        source = _build_item_source("saryn_prime_set")

        self.assertIsNotNone(source)
        assert source is not None
        self.assertEqual(source["name"], "Saryn Prime Set")
        self.assertEqual(source["tier"], "S")

    @patch("agents.market.agent._run_agent", return_value="Saryn Prime Set sells for 80p.")
    @patch("agents.market.agent._build_item_source")
    def test_answer_returns_sources_with_tier(self, mock_source, _mock_run) -> None:
        from agents.market.agent import _session_meta

        mock_source.return_value = {
            "name": "Saryn Prime Set",
            "description": "Prime warframe set.",
            "tier": "S",
            "image_url": "https://example.com/saryn.png",
            "wiki_link": "",
            "drop_sources": [],
        }
        _session_meta["tier-test"] = {
            "tier": "S",
            "resolved_slug": "saryn_prime_set",
            "item_name": "Saryn Prime Set",
        }

        out = answer("price of saryn prime set", session_id="tier-test")

        self.assertEqual(out["tier"], "S")
        self.assertEqual(out["resolved_slug"], "saryn_prime_set")
        self.assertEqual(len(out["sources"]), 1)
        self.assertEqual(out["sources"][0]["tier"], "S")


if __name__ == "__main__":
    unittest.main()
