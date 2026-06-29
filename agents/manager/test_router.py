"""Router classification tests (offline with mocked WFM and LLM)."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from agents.manager.router import build_routing_context, classify

SARYN_HITS = [{"slug": "saryn_prime_set", "name": "Saryn Prime Set"}]
NO_HITS: list[dict] = []

BASE_CONTEXT = {
    "keyword_flags": {
        "forecast": False,
        "timing": False,
        "live_market": False,
        "portfolio": False,
        "recommend": False,
    },
    "wfm_matches": [],
    "item_query": "Saryn",
    "warframe": {
        "frames_mentioned": ["Saryn"],
        "warframe_variant": "base",
        "is_warframe_query": True,
    },
}

PRIME_CONTEXT = {
    "keyword_flags": {
        "forecast": False,
        "timing": False,
        "live_market": False,
        "portfolio": False,
        "recommend": False,
    },
    "wfm_matches": [{"name": "Saryn Prime Set", "slug": "saryn_prime_set"}],
    "item_query": "Saryn Prime Set",
    "warframe": {
        "frames_mentioned": ["Saryn Prime"],
        "warframe_variant": "prime",
        "is_warframe_query": True,
    },
}


class RouterTests(unittest.TestCase):
    @patch("agents.manager.router.find_items_in_text")
    @patch("agents.manager.router.search")
    def test_buy_timing_routes_to_forecasting(self, mock_search, mock_find):
        mock_find.return_value = SARYN_HITS
        mock_search.return_value = {"results": SARYN_HITS}

        plan = classify("when is a good time to buy saryn prime")

        self.assertEqual(plan.agent, "forecasting")
        self.assertEqual(plan.reason, "forecast_keywords")

    @patch("agents.manager.router.classify_with_llm")
    @patch("agents.manager.router.build_routing_context")
    def test_llm_live_orders_routes_to_market(self, mock_context, mock_llm):
        mock_context.return_value = {
            **PRIME_CONTEXT,
            "keyword_flags": {**PRIME_CONTEXT["keyword_flags"], "live_market": True},
        }
        mock_llm.return_value = {
            "primary_agent": "market",
            "item_query": "Saryn Prime Set",
            "needs_forecast": False,
            "reason": "live_orders",
        }

        plan = classify("what are live sell orders for saryn prime")

        self.assertEqual(plan.agent, "market")
        self.assertEqual(plan.reason, "live_orders")

    @patch("agents.manager.router.classify_with_llm")
    @patch("agents.manager.router.build_routing_context")
    def test_llm_wfm_miss_can_still_return_knowledge(self, mock_context, mock_llm):
        mock_context.return_value = BASE_CONTEXT
        mock_llm.return_value = {
            "primary_agent": "knowledge",
            "item_query": "Saryn",
            "needs_forecast": False,
            "reason": "base_frame_abilities",
        }

        plan = classify("tell me about saryn abilities")

        self.assertEqual(plan.agent, "knowledge")
        self.assertEqual(plan.reason, "base_frame_abilities")

    @patch("agents.manager.router.classify_with_llm")
    @patch("agents.manager.router.build_routing_context")
    def test_llm_knowledge_overridden_when_wfm_hit(self, mock_context, mock_llm):
        mock_context.return_value = PRIME_CONTEXT
        mock_llm.return_value = {
            "primary_agent": "knowledge",
            "item_query": "Saryn Prime",
            "needs_forecast": False,
            "reason": "prime_abilities_lore",
        }

        plan = classify("tell me about saryn prime abilities")

        self.assertEqual(plan.agent, "market")
        self.assertEqual(plan.reason, "llm_knowledge_overridden_wfm_hit")

    @patch("agents.manager.router.classify_with_llm")
    @patch("agents.manager.router.build_routing_context")
    def test_llm_prime_vaulted_routes_to_market(self, mock_context, mock_llm):
        mock_context.return_value = PRIME_CONTEXT
        mock_llm.return_value = {
            "primary_agent": "market",
            "item_query": "Saryn Prime Set",
            "needs_forecast": False,
            "warframe_variant": "prime",
            "reason": "prime_vaulted_status",
        }

        plan = classify("is saryn prime vaulted")

        self.assertEqual(plan.agent, "market")
        self.assertEqual(plan.reason, "prime_vaulted_status")

    @patch("agents.manager.router.find_items_in_text")
    @patch("agents.manager.router.search")
    def test_forecast_trend_routes_to_forecasting(self, mock_search, mock_find):
        mock_find.return_value = SARYN_HITS
        mock_search.return_value = {"results": SARYN_HITS}

        plan = classify("forecast saryn prime median trend")

        self.assertEqual(plan.agent, "forecasting")
        self.assertEqual(plan.reason, "forecast_keywords")

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False)
    @patch("agents.manager.router.classify_with_llm", return_value=None)
    @patch("agents.manager.router.build_routing_context")
    def test_no_api_key_fallback_base_warframe_routes_to_market(self, mock_context, _mock_llm):
        mock_context.return_value = BASE_CONTEXT

        plan = classify("tell me about saryn abilities")

        self.assertEqual(plan.agent, "market")
        self.assertEqual(plan.reason, "fallback_default_market")

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False)
    @patch("agents.manager.router.classify_with_llm", return_value=None)
    @patch("agents.manager.router.build_routing_context")
    def test_recommend_routes_to_market(self, mock_context, _mock_llm):
        mock_context.return_value = {
            **BASE_CONTEXT,
            "keyword_flags": {**BASE_CONTEXT["keyword_flags"], "recommend": True},
        }

        plan = classify("recommend a good prime warframe to buy")

        self.assertEqual(plan.agent, "market")
        self.assertEqual(plan.reason, "recommend_market")

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False)
    @patch("agents.manager.router.classify_with_llm", return_value=None)
    @patch("agents.manager.router.build_routing_context")
    def test_no_api_key_fallback_prime_warframe(self, mock_context, _mock_llm):
        mock_context.return_value = PRIME_CONTEXT

        plan = classify("is saryn prime vaulted")

        self.assertEqual(plan.agent, "market")
        self.assertEqual(plan.reason, "fallback_prime_warframe")

    @patch("agents.manager.router._extract_item_query", return_value="Saryn Prime Set")
    @patch("agents.manager.router.find_items_in_text")
    @patch("agents.manager.router._warframe_routing_hint")
    def test_build_routing_context_includes_wfm_and_warframe(
        self, mock_warframe, mock_find, _mock_extract
    ):
        mock_find.return_value = SARYN_HITS
        mock_warframe.return_value = PRIME_CONTEXT["warframe"]

        context = build_routing_context(
            "is saryn prime vaulted",
            conversation=[{"role": "user", "content": "hi"}],
            session_meta={"last_item": "Saryn Prime"},
        )

        self.assertTrue(context["wfm_matches"])
        self.assertEqual(context["item_query"], "Saryn Prime Set")
        self.assertEqual(context["warframe"]["warframe_variant"], "prime")
        self.assertEqual(context["session_meta"]["last_item"], "Saryn Prime")
        self.assertEqual(len(context["recent_conversation"]), 1)

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False)
    @patch("agents.manager.router.classify_with_llm", return_value=None)
    @patch("agents.manager.router.find_items_in_text", return_value=[])
    @patch("agents.manager.router.build_routing_context")
    def test_followup_price_with_session_meta_routes_to_market(
        self, mock_context, _mock_find, _mock_llm
    ):
        mock_context.return_value = {
            **BASE_CONTEXT,
            "item_query": "",
            "session_meta": {"last_item": "Saryn Prime", "last_agent": "knowledge"},
        }

        plan = classify(
            "how much does she cost",
            conversation=[
                {"role": "user", "content": "who is saryn prime"},
                {"role": "assistant", "content": "Saryn Prime is a warframe."},
            ],
            session_meta={"last_item": "Saryn Prime", "last_agent": "knowledge"},
        )

        self.assertEqual(plan.agent, "market")
        self.assertEqual(plan.item_query, "Saryn Prime")
        self.assertEqual(plan.reason, "fallback_followup_context")


if __name__ == "__main__":
    unittest.main()
