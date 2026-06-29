"""Knowledge agent reply generation tests."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

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
    def test_hit_generates_reply_and_sources(self, mock_retrieve, _mock_enrich) -> None:
        mock_retrieve.return_value = ([SARYN_HIT], None)

        cfg = {"chat_model": "gpt-4o-mini", "temperature": 0.3, "max_history": 20}
        client = MagicMock()
        client.chat.completions.create.return_value.choices[0].message.content = (
            "Saryn Prime is a toxic warframe, Operator."
        )

        with patch("agents.knowledge.agent._get_client", return_value=(cfg, client)):
            result = answer("who is saryn prime")

        client.chat.completions.create.assert_called_once()
        self.assertEqual(result["reply"], "Saryn Prime is a toxic warframe, Operator.")
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
