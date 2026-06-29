"""Tier store lookup tests."""
from __future__ import annotations

import unittest

from agents.ranking.tier_store import lookup_tier_from_wfm, tier_slug_candidates


class TierStoreTests(unittest.TestCase):
    def test_tier_slug_candidates_strips_set_and_prime(self) -> None:
        candidates = tier_slug_candidates("saryn_prime_set")
        self.assertIn("saryn_prime_set", candidates)
        self.assertIn("saryn_prime", candidates)
        self.assertIn("saryn", candidates)

    def test_saryn_prime_set_resolves_to_s_tier(self) -> None:
        tier = lookup_tier_from_wfm("saryn_prime_set", ["warframe"])
        self.assertEqual(tier, "S")

    def test_saryn_prime_blueprint_resolves_to_s_tier(self) -> None:
        tier = lookup_tier_from_wfm("saryn_prime_blueprint", ["warframe"])
        self.assertEqual(tier, "S")


if __name__ == "__main__":
    unittest.main()
