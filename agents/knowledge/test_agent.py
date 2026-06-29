"""Knowledge agent card-only reply tests."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from agents.knowledge.agent import answer

SARYN_HIT = {
    "slug": "saryn_prime",
    "doc_id": "saryn_prime",
    "name": "Saryn Prime",
    "description": "Enhanced toxic warframe.",
    "equipment_class": "warframes",
    "image_url": "https://example.com/saryn.png",
    "wiki_link": "https://wiki.warframe.com/w/Saryn/Prime",
    "drop_sources": [],
}


class KnowledgeAnswerTests(unittest.TestCase):
    @patch("agents.knowledge.agent.enrich_hit_drops", side_effect=lambda h: h)
    @patch("agents.knowledge.agent.retrieve")
    def test_hit_returns_empty_reply_and_sources(self, mock_retrieve, _mock_enrich) -> None:
        mock_retrieve.return_value = ([SARYN_HIT], None)

        with patch("agents.knowledge.agent._get_client") as mock_client:
            result = answer("who is saryn prime")

        mock_client.assert_not_called()
        self.assertEqual(result["reply"], "")
        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(result["sources"][0]["name"], "Saryn Prime")

    @patch("agents.knowledge.agent.retrieve")
    def test_miss_returns_static_message(self, mock_retrieve) -> None:
        mock_retrieve.return_value = ([], None)

        with patch("agents.knowledge.agent._get_client") as mock_client:
            result = answer("xyznotarealitem999")

        mock_client.assert_not_called()
        self.assertIn("No matching items", result["reply"])
        self.assertEqual(result["sources"], [])


if __name__ == "__main__":
    unittest.main()
