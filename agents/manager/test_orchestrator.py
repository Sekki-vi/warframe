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
        # Market defers out-of-scope lore questions to Knowledge.
        mock_market.return_value = {
            "response": "",
            "resolved_slug": "",
            "needs_knowledge": True,
        }
        mock_knowledge.return_value = {
            "reply": "Saryn is a toxic warframe, Operator.",
            "sources": [{"name": "Saryn", "description": "Toxic frame."}],
            "resolved_slug": "saryn",
        }
        mock_enrich.side_effect = lambda r: r
        mock_format.return_value = "Saryn is a toxic warframe, Operator."
        mock_sources.return_value = [{"name": "Saryn", "description": "Toxic frame."}]

        out = handle_query("tell me about saryn abilities", "user", "orch-test")

        mock_market.assert_called_once()
        mock_knowledge.assert_called_once()
        self.assertEqual(out["agents_called"][:2], ["market", "knowledge"])
        self.assertTrue(out.get("sources"))
        self.assertIn("toxic warframe", out["response"])

    @patch("agents.manager.orchestrator.find_items_in_text", return_value=[])
    @patch("agents.manager.orchestrator.market_answer")
    @patch("agents.manager.orchestrator.knowledge_answer")
    @patch("agents.manager.orchestrator.enrich_response")
    @patch("agents.manager.orchestrator.format_knowledge_reply")
    @patch("agents.manager.orchestrator.knowledge_sources")
    @patch("agents.manager.orchestrator.classify")
    def test_knowledge_backup_when_market_resolves_but_cant_answer(
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
        # Market resolved an item but doesn't actually know the answer.
        mock_market.return_value = {
            "response": "I don't have information on Baruuk's passive.",
            "resolved_slug": "baruuk",
        }
        mock_knowledge.return_value = {
            "reply": "Baruuk's passive builds Restraint, Operator.",
            "sources": [{"name": "Baruuk", "description": "Peaceful frame."}],
            "resolved_slug": "baruuk",
        }
        mock_enrich.side_effect = lambda r: r
        mock_format.return_value = "Baruuk's passive builds Restraint, Operator."
        mock_sources.return_value = [{"name": "Baruuk", "description": "Peaceful frame."}]

        out = handle_query("baruuk passive effect", "user", "orch-test")

        mock_market.assert_called_once()
        mock_knowledge.assert_called_once()
        self.assertEqual(out["agents_called"][:2], ["market", "knowledge"])
        self.assertIn("Restraint", out["response"])

    @patch("agents.manager.orchestrator.find_items_in_text", return_value=[])
    @patch("agents.manager.orchestrator.market_answer")
    @patch("agents.manager.orchestrator.knowledge_answer")
    @patch("agents.manager.orchestrator.classify")
    def test_no_knowledge_backup_for_recommendations(
        self,
        mock_classify,
        mock_knowledge,
        mock_market,
        _mock_find,
    ):
        from agents.manager.router import RoutePlan

        mock_classify.return_value = RoutePlan(agent="market", reason="recommend_market")
        mock_market.return_value = {
            "response": "Here are some prime warframes to consider...",
            "resolved_slug": "",
        }

        out = handle_query("recommend a good prime warframe to buy", "user", "orch-test")

        mock_market.assert_called_once()
        mock_knowledge.assert_not_called()
        self.assertEqual(out["agents_called"], ["market"])

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
            "tier": "S",
            "sources": [{
                "name": "Saryn Prime Set",
                "description": "Prime warframe set.",
                "tier": "S",
                "image_url": "https://example.com/saryn.png",
                "wiki_link": "",
                "drop_sources": [],
            }],
        }

        out = handle_query("is saryn prime vaulted", "user", "orch-test")

        mock_market.assert_called_once()
        mock_knowledge.assert_not_called()
        self.assertEqual(out["agents_called"], ["market", "ranking"])
        self.assertEqual(out["sources"][0]["tier"], "S")


if __name__ == "__main__":
    unittest.main()
