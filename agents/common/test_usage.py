"""Token usage tracker tests."""
from __future__ import annotations

import unittest

from agents.common import usage


class _Usage:
    """Minimal stand-in for an OpenAI response.usage object."""

    def __init__(self, prompt: int, completion: int) -> None:
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = prompt + completion


class UsageTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        usage.reset()

    def tearDown(self) -> None:
        usage.reset()

    def test_record_accumulates_total_agent_and_model(self) -> None:
        usage.record("gpt-4o-mini", _Usage(10, 5), agent="market")
        usage.record("gpt-4o-mini", _Usage(20, 0), agent="knowledge")

        snap = usage.snapshot()
        self.assertEqual(snap["total"], {"prompt": 30, "completion": 5, "total": 35, "calls": 2})
        self.assertEqual(snap["by_agent"]["market"]["total"], 15)
        self.assertEqual(snap["by_agent"]["knowledge"]["total"], 20)
        self.assertEqual(snap["by_model"]["gpt-4o-mini"]["calls"], 2)

    def test_record_handles_none_and_embedding_usage(self) -> None:
        usage.record("m", None, agent="router")  # no-op
        usage.record("text-embedding-3-small", {"prompt_tokens": 8, "total_tokens": 8}, agent="knowledge")

        snap = usage.snapshot()
        self.assertEqual(snap["total"]["total"], 8)
        self.assertEqual(snap["total"]["completion"], 0)
        self.assertEqual(snap["total"]["calls"], 1)

    def test_delta_since(self) -> None:
        usage.record("m", _Usage(100, 50), agent="market")
        before = usage.total_bucket()
        usage.record("m", _Usage(10, 4), agent="forecasting")

        delta = usage.delta_since(before)
        self.assertEqual(delta, {"prompt": 10, "completion": 4, "total": 14, "calls": 1})


if __name__ == "__main__":
    unittest.main()
