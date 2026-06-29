"""Manager response formatting tests."""
from __future__ import annotations

import unittest

from agents.manager.responses import format_knowledge_reply


class ResponseFormatTests(unittest.TestCase):
    def test_empty_reply_when_sources_present(self) -> None:
        result = {
            "reply": "I do not have enough context.",
            "sources": [{"name": "Saryn Prime", "description": "A warframe."}],
        }
        self.assertEqual(format_knowledge_reply(result), "")

    def test_reply_when_no_sources(self) -> None:
        result = {"reply": "No matching items were found in the knowledge corpus."}
        self.assertEqual(format_knowledge_reply(result), result["reply"])


if __name__ == "__main__":
    unittest.main()
