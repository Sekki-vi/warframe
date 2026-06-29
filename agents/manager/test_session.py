"""Unified session memory tests."""
from __future__ import annotations

import unittest

from agents.manager import session


class SessionTests(unittest.TestCase):
    def setUp(self) -> None:
        session.clear_session("test-session")

    def tearDown(self) -> None:
        session.clear_session("test-session")

    def test_append_turn_and_get_conversation(self) -> None:
        session.append_turn(
            "test-session",
            "who is saryn prime",
            "Saryn Prime is a warframe.",
            agent="knowledge",
            item_name="Saryn Prime",
            item_slug="saryn_prime",
        )
        conv = session.get_conversation("test-session")
        self.assertEqual(len(conv), 2)
        self.assertEqual(conv[0]["role"], "user")
        self.assertEqual(conv[1]["role"], "assistant")

    def test_session_meta_tracks_last_item(self) -> None:
        session.append_turn(
            "test-session",
            "who is saryn prime",
            "Answer",
            agent="knowledge",
            item_name="Saryn Prime",
            item_slug="saryn_prime",
        )
        meta = session.get_session_meta("test-session")
        self.assertEqual(meta["last_item"], "Saryn Prime")
        self.assertEqual(meta["last_item_slug"], "saryn_prime")
        self.assertEqual(meta["last_agent"], "knowledge")

    def test_clear_session_wipes_memory(self) -> None:
        session.append_turn("test-session", "hi", "hello", agent="knowledge")
        session.clear_session("test-session")
        self.assertEqual(session.get_conversation("test-session"), [])
        self.assertEqual(session.get_session_meta("test-session"), {})


if __name__ == "__main__":
    unittest.main()
