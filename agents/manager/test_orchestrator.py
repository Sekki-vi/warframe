"""Orchestrator follow-up context tests."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from agents.manager import session
from agents.manager.orchestrator import handle_query


class OrchestratorContextTests(unittest.TestCase):
    def setUp(self) -> None:
        session.clear_session("orch-test")

    def tearDown(self) -> None:
        session.clear_session("orch-test")

    @patch("agents.manager.orchestrator.find_items_in_text", return_value=[])
    @patch("agents.manager.orchestrator.market_answer")
    @patch("agents.manager.orchestrator.knowledge_answer")
    @patch("agents.manager.orchestrator.enrich_response")
    @patch("agents.manager.orchestrator.format_knowledge_reply")
    @patch("agents.manager.orchestrator.knowledge_sources")
    @patch("agents.manager.orchestrator.classify")
    def test_followup_routes_to_market_with_enriched_message(
        self,
        mock_classify,
        mock_sources,
        mock_format,
        mock_enrich,
        mock_knowledge,
        mock_market,
        _mock_find,
    ):
        from agents.manager.router import RoutePlan

        mock_classify.side_effect = [
            RoutePlan(agent="market", reason="default_market"),
            RoutePlan(
                agent="market",
                item_query="Saryn Prime Set",
                reason="followup_price",
            ),
        ]
        mock_market.return_value = {
            "response": "Cheapest sell is 80p.",
            "resolved_slug": "saryn_prime_set",
        }

        handle_query("who is saryn prime", "user", "orch-test")
        handle_query("how much does she cost", "user", "orch-test")

        self.assertEqual(mock_market.call_count, 2)
        market_message = mock_market.call_args[0][0]
        self.assertIn("Saryn Prime", market_message)
        self.assertIn("how much does she cost", market_message.lower())
        mock_knowledge.assert_not_called()

        meta = session.get_session_meta("orch-test")
        self.assertEqual(meta.get("last_item"), "Saryn Prime Set")

    @patch("agents.manager.orchestrator.find_items_in_text", return_value=[])
    @patch("agents.manager.orchestrator.market_answer")
    @patch("agents.manager.orchestrator.knowledge_answer")
    @patch("agents.manager.orchestrator.enrich_response")
    @patch("agents.manager.orchestrator.format_knowledge_reply")
    @patch("agents.manager.orchestrator.knowledge_sources")
    @patch("agents.manager.orchestrator.classify")
    def test_knowledge_backup_when_market_unresolved(
        self,
        mock_classify,
        mock_sources,
        mock_format,
        mock_enrich,
        mock_knowledge,
        mock_market,
        _mock_find,
    ):
        from agents.manager.router import RoutePlan

        mock_classify.return_value = RoutePlan(agent="market", reason="default_market")
        mock_market.return_value = {"response": "Could not find item.", "resolved_slug": ""}
        mock_knowledge.return_value = {
            "reply": "",
            "sources": [{"name": "Saryn", "description": "Toxic frame."}],
            "resolved_slug": "saryn",
        }
        mock_enrich.side_effect = lambda r: r
        mock_format.return_value = ""
        mock_sources.return_value = [{"name": "Saryn", "description": "Toxic frame."}]

        out = handle_query("tell me about saryn abilities", "user", "orch-test")

        mock_market.assert_called_once()
        mock_knowledge.assert_called_once()
        self.assertEqual(out["agents_called"][:2], ["market", "knowledge"])
        self.assertTrue(out.get("sources"))

    @patch("agents.manager.orchestrator.find_items_in_text", return_value=[])
    @patch("agents.manager.orchestrator.market_answer")
    @patch("agents.manager.orchestrator.knowledge_answer")
    @patch("agents.manager.orchestrator.classify")
    def test_no_knowledge_backup_when_market_resolves(
        self,
        mock_classify,
        mock_knowledge,
        mock_market,
        _mock_find,
    ):
        from agents.manager.router import RoutePlan

        mock_classify.return_value = RoutePlan(agent="market", reason="default_market")
        mock_market.return_value = {
            "response": "Saryn Prime Set is not vaulted.",
            "resolved_slug": "saryn_prime_set",
        }

        out = handle_query("is saryn prime vaulted", "user", "orch-test")

        mock_market.assert_called_once()
        mock_knowledge.assert_not_called()
        self.assertEqual(out["agents_called"], ["market"])


if __name__ == "__main__":
    unittest.main()
